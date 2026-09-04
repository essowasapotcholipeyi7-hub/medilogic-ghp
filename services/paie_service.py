# services/paie_service.py
# ============================================================
# MOTEUR DE CALCUL DE LA PAIE (CNSS / INAM / IRPP — Togo)
# ============================================================
# ⚠️ Les taux utilisés viennent de ParametragePaie (modifiable dans l'écran
# "Paramètres de paie"). Les valeurs par défaut sont indicatives — à faire
# valider par votre comptable / la DGI avant la première paie réelle.

from datetime import date
from decimal import Decimal
from models import db, Paie, ParametragePaie, Employe, Depense


def _d(v):
    """Convertit en float en tolérant None/Decimal/str."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def calculer_irpp(base_imposable, tranches):
    """Calcule l'IRPP par application successive du barème progressif."""
    if base_imposable <= 0 or not tranches:
        return 0.0

    impot = 0.0
    for tranche in sorted(tranches, key=lambda t: t.get('min', 0)):
        seuil_min = _d(tranche.get('min'))
        seuil_max = tranche.get('max')
        seuil_max = _d(seuil_max) if seuil_max is not None else None
        taux = _d(tranche.get('taux')) / 100.0

        if base_imposable <= seuil_min:
            continue

        haut_tranche = min(base_imposable, seuil_max) if seuil_max is not None else base_imposable
        montant_tranche = max(0.0, haut_tranche - seuil_min)
        impot += montant_tranche * taux

    return round(impot, 2)


def calculer_paie(salaire_base, primes, indemnites, parametrage):
    """Calcule un bulletin de paie complet à partir du brut et du
    paramétrage. Ne persiste rien — fonction pure, testable isolément."""
    salaire_base = _d(salaire_base)
    primes = _d(primes)
    indemnites = _d(indemnites)
    brut = salaire_base + primes + indemnites

    plafond_cnss = _d(parametrage.plafond_cnss) or brut
    base_cnss = min(brut, plafond_cnss)

    cnss_salarial = round(base_cnss * _d(parametrage.taux_cnss_salarial) / 100.0, 2)
    cnss_patronal = round(base_cnss * _d(parametrage.taux_cnss_patronal) / 100.0, 2)

    inam_salarial = round(brut * _d(parametrage.taux_inam_salarial) / 100.0, 2)
    inam_patronal = round(brut * _d(parametrage.taux_inam_patronal) / 100.0, 2)

    # Base imposable IRPP = brut moins les cotisations sociales salariales
    base_imposable = max(0.0, brut - cnss_salarial - inam_salarial)
    irpp = calculer_irpp(base_imposable, parametrage.tranches_irpp or [])

    total_retenues = round(cnss_salarial + inam_salarial + irpp, 2)
    total_charges_patronales = round(cnss_patronal + inam_patronal, 2)
    net_a_payer = round(brut - total_retenues, 2)

    return {
        'salaire_base': salaire_base,
        'primes': primes,
        'indemnites': indemnites,
        'salaire_brut': round(brut, 2),
        'cnss_salarial': cnss_salarial,
        'cnss_patronal': cnss_patronal,
        'inam_salarial': inam_salarial,
        'inam_patronal': inam_patronal,
        'irpp': irpp,
        'total_retenues': total_retenues,
        'total_charges_patronales': total_charges_patronales,
        'net_a_payer': net_a_payer,
    }


def generer_ou_maj_paie(structure_id, employe_id, annee, mois, primes=0, indemnites=0, user_nom='System'):
    """Crée (ou recalcule si encore en brouillon) le bulletin de paie d'un
    employé pour une période donnée."""
    employe = Employe.query.get(employe_id)
    if not employe:
        return None, "Employé introuvable"

    parametrage = ParametragePaie.get_ou_creer(structure_id)
    calc = calculer_paie(employe.salaire_base, primes, indemnites, parametrage)

    paie = Paie.query.filter_by(employe_id=employe_id, annee=annee, mois=mois).first()
    if paie and paie.statut == 'payee':
        return None, "Cette paie a déjà été payée — impossible de la recalculer"

    if not paie:
        paie = Paie(structure_id=structure_id, employe_id=employe_id, annee=annee, mois=mois,
                     created_by=user_nom)
        db.session.add(paie)

    for champ, valeur in calc.items():
        setattr(paie, champ, valeur)
    paie.statut = 'valide'

    db.session.commit()
    return paie, None


def marquer_paie_payee(paie, mode_paiement='especes', user_nom='System'):
    """Marque une paie comme payée : crée la Dépense correspondante puis
    l'écriture comptable auto-validée (Débit 661/664, Crédit trésorerie/43)."""
    if paie.statut == 'payee':
        return paie, None

    employe = paie.employe

    depense = Depense(
        structure_id=paie.structure_id,
        montant=_d(paie.net_a_payer),
        motif='salaire',
        motif_personnalise=f"Salaire {paie.get_periode_label()} — {employe.nom} {employe.prenom}",
        description=f"Bulletin de paie #{paie.id}",
        created_by_nom=user_nom,
    )
    db.session.add(depense)
    db.session.flush()

    paie.statut = 'payee'
    paie.mode_paiement = mode_paiement
    paie.date_paiement = date.today()
    paie.depense_id = depense.id
    db.session.commit()

    try:
        from services.comptabilite_service import generer_ecriture_paie
        ecriture = generer_ecriture_paie(paie, employe, user_nom=user_nom)
        if ecriture:
            paie.ecriture_id = ecriture.id
            db.session.commit()
    except Exception as e:
        print(f"⚠️ Erreur génération écriture comptable (paie #{paie.id} conservée payée): {e}")

    try:
        from services.journal_service import JournalService
        JournalService.creer_mouvement(
            structure_id=paie.structure_id, categorie='salaire_paye',
            description=f"Salaire {paie.get_periode_label()} payé — {employe.nom} {employe.prenom}",
            montant=_d(paie.net_a_payer), type_montant='debit',
            reference_type='paie', reference_id=paie.id,
            utilisateur_nom=user_nom,
        )
    except Exception as e:
        print(f"⚠️ Erreur journal d'activité (paie #{paie.id}): {e}")

    return paie, None
