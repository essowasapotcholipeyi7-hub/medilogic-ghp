# services/comptabilite_service.py
# ============================================================
# MOTEUR DE GÉNÉRATION AUTOMATIQUE DES ÉCRITURES COMPTABLES
# ============================================================
# Remplace la logique morte de scripts/generer_ecritures*.py par un
# générateur SYNCHRONE, PAR TRANSACTION (une écriture par vente / paiement /
# dépense — traçabilité fine, "journal de chaque acte").
#
# Règle : toute écriture générée par ce module est automatiquement VALIDÉE
# (statut='valide'), car elle reflète une opération déjà entièrement
# déterminée par le système (vente, encaissement, dépense...). Seules les
# écritures saisies manuellement par un comptable (routes/comptabilite.py,
# POST /compta/api/ecritures) suivent le circuit de validation humaine
# (brouillon -> en_attente -> validee), qui reste inchangé.
#
# Toute fonction publique de ce module est "safe by design" pour l'appelant :
# elle ne lève jamais d'exception vers la route métier (vente, paiement...).
# En cas d'erreur, elle journalise et retourne None — la vente/le paiement
# doit toujours réussir même si la comptabilisation échoue ; l'anomalie est
# alors visible dans le tableau de bord comptabilité pour reprise manuelle.

from datetime import datetime, date
from models import (
    db, CompteComptable, EcritureComptable, LigneEcriture,
    Vente, Facture, PaiementFacture, FactureAssurance,
    AnnulationVente, Recette, Depense
)
from utils.plan_comptable_syscohada import (
    PLAN_COMPTABLE_PAR_NUMERO, COMPTE_CLIENTS_PATIENTS, COMPTE_ATTENTE,
    compte_assurance
)
from utils.categorisation import categoriser_acte

# ============================================================
# RÉSOLUTION / CRÉATION DES COMPTES (avec cache mémoire)
# ============================================================

_compte_cache = {}


def _to_float(v):
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _get_compte(structure_id, numero, nom_repli=None, type_repli='charge'):
    """Résout un CompteComptable par numéro pour une structure, en le créant
    à la volée (à partir du plan SYSCOHADA de référence, ou d'un repli) s'il
    n'existe pas encore — robustesse si le seed n'a pas encore tourné pour
    cette structure."""
    cle = f"{structure_id}_{numero}"
    if cle in _compte_cache:
        return _compte_cache[cle]

    compte = CompteComptable.query.filter_by(structure_id=structure_id, numero=numero).first()
    if compte and not compte.actif:
        compte.actif = True
    if not compte:
        definition = PLAN_COMPTABLE_PAR_NUMERO.get(numero)
        compte = CompteComptable(
            structure_id=structure_id,
            numero=numero,
            nom=definition['nom'] if definition else (nom_repli or numero),
            type=definition['type'] if definition else type_repli,
            classe=definition['classe'] if definition else numero[0]
        )
        db.session.add(compte)
        db.session.flush()  # pour obtenir compte.id sans committer

    _compte_cache[cle] = compte
    return compte


def invalider_cache_comptes():
    _compte_cache.clear()


# ============================================================
# NOYAU COMMUN : CRÉATION D'UNE ÉCRITURE
# ============================================================

def creer_ecriture(structure_id, date_ecriture, libelle, lignes, journal_code,
                    piece_justificative=None, auto=True, source_type=None,
                    source_id=None, commentaire=None, user_nom='SYSTEME'):
    """
    Crée une écriture comptable équilibrée.

    lignes : liste de dicts {numero_compte, libelle, debit=0, credit=0}
    auto=True  -> écriture générée automatiquement, validée immédiatement.
    auto=False -> comportement du circuit manuel existant (brouillon).

    Retourne l'EcritureComptable créée, ou None si l'équilibre débit/crédit
    n'est pas respecté (aucune écriture déséquilibrée n'est jamais persistée).
    """
    lignes_valides = [l for l in lignes if _to_float(l.get('debit')) > 0.005 or _to_float(l.get('credit')) > 0.005]
    if not lignes_valides:
        return None

    total_debit = sum(_to_float(l.get('debit')) for l in lignes_valides)
    total_credit = sum(_to_float(l.get('credit')) for l in lignes_valides)

    if abs(total_debit - total_credit) > 1:  # tolérance d'arrondi (1 FCFA)
        print(f"⚠️ [comptabilite_service] Écriture déséquilibrée rejetée "
              f"(débit={total_debit}, crédit={total_credit}) — {libelle}")
        return None

    if not isinstance(date_ecriture, date):
        date_ecriture = datetime.utcnow().date()

    ecriture = EcritureComptable(
        structure_id=structure_id,
        date_ecriture=date_ecriture,
        libelle=libelle,
        piece_justificative=piece_justificative,
        journal_code=journal_code,
        source_type=source_type,
        source_id=source_id,
        commentaire=commentaire,
        created_by_nom=user_nom,
    )

    if auto:
        ecriture.statut = 'valide'
        ecriture.generee_auto = True
        ecriture.validated_by_nom = 'Validation automatique'
        ecriture.date_validation = datetime.utcnow().date()
    else:
        ecriture.statut = 'brouillon'

    db.session.add(ecriture)
    db.session.flush()

    for l in lignes_valides:
        compte = _get_compte(structure_id, l['numero_compte'])
        db.session.add(LigneEcriture(
            ecriture_id=ecriture.id,
            compte_id=compte.id,
            debit=round(_to_float(l.get('debit')), 2),
            credit=round(_to_float(l.get('credit')), 2),
            libelle=l.get('libelle') or libelle
        ))

    db.session.commit()
    return ecriture


def _compte_tresorerie(mode_paiement):
    """'especes' -> Caisse (571). Tout le reste (carte, mobile money,
    chèque, virement...) -> Banque (521)."""
    if (mode_paiement or 'especes').strip().lower() == 'especes':
        return '571'
    return '521'


def _contre_passer(ecriture_origine, libelle, source_type, source_id, user_nom='SYSTEME'):
    """Crée une écriture miroir (débit <-> crédit inversés) qui annule une
    écriture d'origine — utilisé pour les annulations de vente."""
    lignes = [{
        'numero_compte': l.compte.numero,
        'libelle': libelle,
        'debit': _to_float(l.credit),
        'credit': _to_float(l.debit),
    } for l in ecriture_origine.lignes]

    return creer_ecriture(
        structure_id=ecriture_origine.structure_id,
        date_ecriture=datetime.utcnow().date(),
        libelle=libelle,
        lignes=lignes,
        journal_code=ecriture_origine.journal_code or 'OD',
        piece_justificative=f"ANNUL-{ecriture_origine.piece_justificative or ecriture_origine.id}",
        auto=True,
        source_type=source_type,
        source_id=source_id,
        commentaire=f"Contre-passation de l'écriture #{ecriture_origine.id}",
        user_nom=user_nom,
    )


# ============================================================
# GÉNÉRATEURS PAR ÉVÉNEMENT MÉTIER
# ============================================================

def generer_ecriture_vente(vente, user_nom='SYSTEME'):
    """Génère l'écriture d'une vente (actes médicaux, pharmacie ou
    lunetterie). Doit être appelée juste après l'insertion de la vente et
    de sa recette associée.

    Débit : trésorerie (encaissé net) + assurance(s) à recevoir + client
            (reste à payer).
    Crédit : ventes, par catégorie (actes) ou globalement (pharmacie).
    """
    try:
        structure_id = vente.structure_id
        montant_donne = _to_float(vente.montant_donne)
        rendu = _to_float(vente.rendu)
        montant_effectif = round(montant_donne - rendu, 2)
        prise_en_charge = _to_float(vente.prise_en_charge)
        prise_en_charge2 = _to_float(vente.prise_en_charge2)
        reste_a_payer = _to_float(vente.reste_a_payer)

        lignes = []
        total_debit = 0.0

        if montant_effectif > 0:
            lignes.append({'numero_compte': _compte_tresorerie(vente.mode_paiement),
                            'libelle': 'Encaissement vente', 'debit': montant_effectif})
            total_debit += montant_effectif

        if prise_en_charge > 0:
            nom_assurance = vente.assurance or (vente.assurances_data or {}).get('principale', {}).get('nom') if hasattr(vente, 'assurances_data') else vente.assurance
            compte_num = compte_assurance(vente.assurance)
            lignes.append({'numero_compte': compte_num,
                            'libelle': f"Tiers-payant à recevoir ({vente.assurance or 'assurance'})",
                            'debit': prise_en_charge})
            total_debit += prise_en_charge

        if prise_en_charge2 > 0:
            compte_num2 = compte_assurance(vente.assurance2_nom)
            lignes.append({'numero_compte': compte_num2,
                            'libelle': f"Tiers-payant à recevoir ({vente.assurance2_nom or 'assurance 2'})",
                            'debit': prise_en_charge2})
            total_debit += prise_en_charge2

        if reste_a_payer > 0.5:
            lignes.append({'numero_compte': COMPTE_CLIENTS_PATIENTS,
                            'libelle': f"Créance client — {vente.patient_nom}",
                            'debit': reste_a_payer})
            total_debit += reste_a_payer

        if total_debit <= 0.5:
            return None  # rien à comptabiliser (ex: vente à 0)

        # --- Répartition du crédit "Ventes" par catégorie ---
        items = vente.actes if (vente.type == 'actes' and vente.actes) else (vente.produits or [])
        totaux_par_compte = {}

        if vente.type in ('pharma', 'pharmacie'):
            totaux_par_compte['7011'] = total_debit
        elif vente.type in ('lunettes', 'lunetterie', 'optique'):
            totaux_par_compte['7012'] = total_debit
        elif items:
            for item in items:
                if not isinstance(item, dict):
                    continue
                nom = item.get('nom', '')
                montant_item = _to_float(item.get('total') or item.get('prix') or item.get('montant'))
                info = categoriser_acte(nom)
                compte_num = info['compte']
                totaux_par_compte[compte_num] = totaux_par_compte.get(compte_num, 0) + montant_item

            somme_items = sum(totaux_par_compte.values())
            if somme_items <= 0.5:
                totaux_par_compte = {'7068': total_debit}
            elif abs(somme_items - total_debit) > 1:
                # Ajustement d'arrondi sur "Autres prestations" pour garantir
                # l'équilibre de l'écriture sans bloquer la vente.
                ecart = round(total_debit - somme_items, 2)
                totaux_par_compte['7068'] = totaux_par_compte.get('7068', 0) + ecart
        else:
            totaux_par_compte['7068'] = total_debit

        for compte_num, montant in totaux_par_compte.items():
            if montant <= 0:
                continue
            lignes.append({'numero_compte': compte_num, 'libelle': f"Ventes — {vente.patient_nom}",
                            'credit': round(montant, 2)})

        libelle = f"Vente {vente.type} #{vente.id} — {vente.patient_nom}"
        ecriture = creer_ecriture(
            structure_id=structure_id,
            date_ecriture=(vente.date_vente.date() if vente.date_vente else datetime.utcnow().date()),
            libelle=libelle,
            lignes=lignes,
            journal_code='VTE',
            piece_justificative=f"VTE-{vente.id}",
            auto=True,
            source_type='vente',
            source_id=vente.id,
            user_nom=user_nom,
        )

        if ecriture:
            vente.ecriture_generee = True
            vente.ecriture_id = ecriture.id
            db.session.commit()

        return ecriture

    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_vente(vente#{getattr(vente, 'id', '?')}): {e}")
        import traceback
        traceback.print_exc()
        return None


def generer_ecriture_annulation_vente(vente, annulation, user_nom='SYSTEME'):
    """Contre-passe l'écriture d'origine d'une vente annulée."""
    try:
        if not vente.ecriture_id:
            return None
        ecriture_origine = EcritureComptable.query.get(vente.ecriture_id)
        if not ecriture_origine:
            return None
        return _contre_passer(
            ecriture_origine,
            libelle=f"Annulation vente #{vente.id} — {vente.patient_nom}",
            source_type='annulation_vente',
            source_id=annulation.id if annulation else vente.id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_annulation_vente: {e}")
        return None


def generer_ecriture_paiement_facture(paiement, facture, user_nom='SYSTEME'):
    """Un client vient régler (totalement ou partiellement) une créance
    déjà reconnue lors de la vente (compte 4111). Débit trésorerie, crédit
    client — c'est ce qui fait redescendre la créance vers zéro."""
    try:
        montant = _to_float(paiement.montant)
        if montant <= 0:
            return None

        lignes = [
            {'numero_compte': _compte_tresorerie(paiement.mode_paiement),
             'libelle': f"Règlement facture {facture.numero_facture}", 'debit': montant},
            {'numero_compte': COMPTE_CLIENTS_PATIENTS,
             'libelle': f"Solde créance — {facture.patient_nom}", 'credit': montant},
        ]

        return creer_ecriture(
            structure_id=facture.structure_id,
            date_ecriture=(paiement.date_paiement.date() if paiement.date_paiement else datetime.utcnow().date()),
            libelle=f"Règlement facture {facture.numero_facture} — {facture.patient_nom}",
            lignes=lignes,
            journal_code='CAI' if _compte_tresorerie(paiement.mode_paiement) == '571' else 'BQ',
            piece_justificative=f"PAI-{paiement.id}",
            auto=True,
            source_type='paiement_facture',
            source_id=paiement.id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_paiement_facture: {e}")
        return None


def generer_ecriture_remboursement_assurance(montant, assurance_nom, structure_id,
                                              reference, source_id, user_nom='SYSTEME'):
    """Un assureur règle (par virement bancaire) le tiers-payant déjà
    reconnu en créance lors des ventes prises en charge. Débit banque,
    crédit compte assurance."""
    try:
        montant = _to_float(montant)
        if montant <= 0:
            return None

        compte_num = compte_assurance(assurance_nom)
        lignes = [
            {'numero_compte': '521', 'libelle': f"Virement {assurance_nom}", 'debit': montant},
            {'numero_compte': compte_num, 'libelle': f"Solde tiers-payant {assurance_nom}", 'credit': montant},
        ]

        return creer_ecriture(
            structure_id=structure_id,
            date_ecriture=datetime.utcnow().date(),
            libelle=f"Remboursement assurance {assurance_nom} — {reference}",
            lignes=lignes,
            journal_code='BQ',
            piece_justificative=f"ASS-{source_id}",
            auto=True,
            source_type='paiement_assurance',
            source_id=source_id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_remboursement_assurance: {e}")
        return None


# Mots-clés de "motif" de dépense (saisis librement dans l'UI) -> compte de charge
_COMPTE_PAR_MOTIF_DEPENSE = {
    'salaire': '661', 'salaires': '661',
    'loyer': '613', 'location': '613',
    'eau': '614', 'electricite': '614', 'électricité': '614',
    'entretien': '615', 'reparation': '615', 'réparation': '615',
    'assurance': '616',
    'transport': '624',
    'carburant': '624',
    'communication': '626', 'telephone': '626', 'téléphone': '626', 'internet': '626',
    'banque': '627', 'frais bancaire': '627',
    'fourniture': '628', 'bureau': '628',
    'impot': '631', 'impôt': '631', 'taxe': '631',
    'medicament': '601', 'médicament': '601', 'pharmacie': '601',
    'materiel': '604', 'matériel': '604', 'equipement': '604', 'équipement': '604',
}


def _compte_charge_pour_motif(motif):
    if not motif:
        return '628'
    cle = str(motif).strip().lower()
    for mot, compte in _COMPTE_PAR_MOTIF_DEPENSE.items():
        if mot in cle:
            return compte
    return '628'  # charge diverse par défaut


def generer_ecriture_depense(depense, user_nom='SYSTEME'):
    """Débit charge (déduite du motif), crédit trésorerie (caisse par
    défaut — les dépenses n'ont pas de mode de paiement dédié dans le
    modèle actuel)."""
    try:
        montant = _to_float(depense.montant)
        if montant <= 0:
            return None

        compte_charge = _compte_charge_pour_motif(depense.motif or depense.motif_personnalise)
        lignes = [
            {'numero_compte': compte_charge, 'libelle': depense.motif or 'Dépense', 'debit': montant},
            {'numero_compte': '571', 'libelle': depense.motif or 'Dépense', 'credit': montant},
        ]

        return creer_ecriture(
            structure_id=depense.structure_id,
            date_ecriture=(depense.date_depense.date() if depense.date_depense else datetime.utcnow().date()),
            libelle=f"Dépense — {depense.motif or depense.motif_personnalise or 'Divers'}",
            lignes=lignes,
            journal_code='ACH',
            piece_justificative=f"DEP-{depense.id}",
            auto=True,
            source_type='depense',
            source_id=depense.id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_depense: {e}")
        return None


def generer_ecriture_recette_diverse(recette, user_nom='SYSTEME'):
    """Pour une recette saisie manuellement (POST /api/finances/recettes),
    non issue d'une vente (qui est déjà comptabilisée par
    generer_ecriture_vente). Débit trésorerie, crédit produits divers."""
    try:
        montant = _to_float(recette.montant)
        if montant <= 0:
            return None

        lignes = [
            {'numero_compte': '571', 'libelle': recette.source or 'Recette', 'debit': montant},
            {'numero_compte': '758', 'libelle': recette.source or 'Recette', 'credit': montant},
        ]

        return creer_ecriture(
            structure_id=recette.structure_id,
            date_ecriture=(recette.date_recette.date() if recette.date_recette else datetime.utcnow().date()),
            libelle=f"Recette diverse — {recette.source or recette.description or ''}",
            lignes=lignes,
            journal_code='CAI',
            piece_justificative=f"REC-{recette.id}",
            auto=True,
            source_type='recette',
            source_id=recette.id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_recette_diverse: {e}")
        return None


def generer_ecriture_paie(paie, employe, user_nom='SYSTEME'):
    """Écriture de paie (charges de personnel + reversements sociaux/fiscaux
    dus + décaissement du net). Une seule écriture couvre la charge et le
    paiement puisque marquer_paie_payee() traite les deux en même temps."""
    try:
        salaire_brut = _to_float(paie.salaire_brut)
        cnss_sal = _to_float(paie.cnss_salarial)
        cnss_pat = _to_float(paie.cnss_patronal)
        inam_sal = _to_float(paie.inam_salarial)
        inam_pat = _to_float(paie.inam_patronal)
        irpp = _to_float(paie.irpp)
        net = _to_float(paie.net_a_payer)

        if salaire_brut <= 0:
            return None

        libelle = f"Paie {paie.get_periode_label()} — {employe.nom} {employe.prenom}"
        lignes = [
            {'numero_compte': '661', 'libelle': 'Salaires et appointements', 'debit': salaire_brut},
        ]
        if cnss_pat > 0:
            lignes.append({'numero_compte': '664', 'libelle': 'Charges sociales CNSS patronal', 'debit': cnss_pat})
        if inam_pat > 0:
            lignes.append({'numero_compte': '6641', 'libelle': 'Charges sociales INAM patronal', 'debit': inam_pat})

        if net > 0:
            lignes.append({'numero_compte': _compte_tresorerie(paie.mode_paiement),
                            'libelle': 'Net payé au salarié', 'credit': net})
        if cnss_sal > 0:
            lignes.append({'numero_compte': '431', 'libelle': 'CNSS salarial à reverser', 'credit': cnss_sal})
        if cnss_pat > 0:
            lignes.append({'numero_compte': '432', 'libelle': 'CNSS patronal à reverser', 'credit': cnss_pat})
        if inam_sal > 0:
            lignes.append({'numero_compte': '433', 'libelle': 'INAM salarial à reverser', 'credit': inam_sal})
        if inam_pat > 0:
            lignes.append({'numero_compte': '434', 'libelle': 'INAM patronal à reverser', 'credit': inam_pat})
        if irpp > 0:
            lignes.append({'numero_compte': '447', 'libelle': 'IRPP à reverser', 'credit': irpp})

        return creer_ecriture(
            structure_id=paie.structure_id,
            date_ecriture=(paie.date_paiement or datetime.utcnow().date()),
            libelle=libelle,
            lignes=lignes,
            journal_code='ACH',
            piece_justificative=f"PAIE-{paie.id}",
            auto=True,
            source_type='paie',
            source_id=paie.id,
            user_nom=user_nom,
        )
    except Exception as e:
        db.session.rollback()
        print(f"❌ [comptabilite_service] Erreur generer_ecriture_paie: {e}")
        return None


# ============================================================
# LES DEUX CAISSES (tableau de bord comptabilité)
# ============================================================

def get_soldes_caisses(structure_id, date_debut=None, date_fin=None):
    """Retourne les deux indicateurs demandés :
    - tresorerie : solde réel disponible (classe 5 : Caisse 571 + Banque 521),
      toutes périodes confondues (c'est un solde, pas un flux).
    - chiffre_affaires : total des ventes (classe 7, comptes 70x) sur la
      période donnée (flux, pas un solde).
    """
    comptes_tresorerie = CompteComptable.query.filter(
        CompteComptable.structure_id == structure_id,
        CompteComptable.numero.in_(['571', '521'])
    ).all()

    tresorerie = 0.0
    detail_tresorerie = []
    for c in comptes_tresorerie:
        solde = _to_float(c.get_solde())
        tresorerie += solde
        detail_tresorerie.append({'numero': c.numero, 'nom': c.nom, 'solde': solde})

    comptes_ca = CompteComptable.query.filter(
        CompteComptable.structure_id == structure_id,
        CompteComptable.numero.like('7%')
    ).all()

    chiffre_affaires = 0.0
    detail_ca = []
    for c in comptes_ca:
        solde = _to_float(c.get_solde(date_debut, date_fin))  # crédit - débit inversé pour un compte de produit
        montant = -solde  # get_solde() = débit - crédit ; un produit est normalement créditeur
        if montant > 0:
            chiffre_affaires += montant
            detail_ca.append({'numero': c.numero, 'nom': c.nom, 'montant': montant})

    return {
        'caisse_tresorerie': round(tresorerie, 2),
        'detail_tresorerie': detail_tresorerie,
        'caisse_chiffre_affaires': round(chiffre_affaires, 2),
        'detail_chiffre_affaires': detail_ca,
    }
