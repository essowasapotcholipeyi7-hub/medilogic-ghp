# offline/routes_ventes.py
"""Création de vente (acte ou pharmacie) hors-ligne.

Capture UNIQUEMENT les faits essentiels de la vente elle-même — jamais les
étapes 2-6 identifiées dans le plan (recette, stock, caisse, part médecin,
demandes labo, écriture comptable) : celles-ci sont rejouées côté serveur
par outbox.push_pending() en réutilisant les fonctions réelles de app.py,
une fois de retour en ligne. Voir le plan, section "Découverte critique".

Vente pharmacie hors-ligne : le stock n'est PAS vérifié (vit dans Google
Sheets, injoignable) — décision actée avec le patron : la vente passe quand
même, avec un avertissement visible côté interface."""

import json
import uuid as uuid_module
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from offline.db_offline import requeter, requeter_une, executer_plusieurs
from offline.config_offline import OFFLINE_STRUCTURE_ID
from offline.auth_offline import utilisateur_connecte, nom_utilisateur

bp_ventes = Blueprint('offline_ventes', __name__)


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _prochain_numero_local_offline():
    """Même principe que routes_patients._prochain_numero_local_offline()
    — repart du dernier numero_local connu sur Neon pour cette structure,
    jamais de zéro."""
    depart = requeter(
        "SELECT numero_local_depart_ventes AS d FROM offline_sync_state WHERE id = 1"
    )
    depart_val = depart[0]['d'] if depart else 0
    local_max = requeter(
        "SELECT COALESCE(MAX(numero_local), 0) AS m FROM offline_ventes WHERE structure_id = ?",
        (OFFLINE_STRUCTURE_ID,)
    )
    local_max_val = local_max[0]['m'] if local_max else 0
    return max(depart_val, local_max_val) + 1


def _creer_vente(data, type_vente, colonne_articles):
    patient_uuid = data.get('patient_uuid')
    if not patient_uuid:
        return None, ('ID patient manquant', 400)

    patient = requeter_une("SELECT * FROM offline_patients WHERE uuid = ?", (patient_uuid,))
    if not patient:
        return None, ('Patient introuvable dans la base locale', 404)

    articles = data.get(colonne_articles, [])
    for article in articles:
        article.setdefault('prise_en_charge_amu', True)
        article.setdefault('prise_en_charge_cac', True)
        article.setdefault('statut', 'direct')

    taux_assurance = float(data.get('taux_assurance') or 0)
    assurance2_nom = data.get('assurance2_nom', '')
    taux_assurance2 = float(data.get('taux_assurance2') or 0)
    societe_assurance2 = data.get('societe_assurance2') or None
    prise_en_charge = float(data.get('prise_en_charge') or 0)
    prise_en_charge2 = float(data.get('prise_en_charge2') or 0)
    montant_donne = float(data.get('montant_donne') or 0)
    rendu = float(data.get('rendu') or 0)
    base_remboursement = float(data.get('base_remboursement') or 0)
    reste_a_payer = float(data.get('reste_a_payer') or 0)
    taux_aide = float(data.get('taux_aide') or 0)
    type_aide = data.get('type_aide', 'pourcentage')
    if type_aide not in ('pourcentage', 'montant'):
        type_aide = 'pourcentage'
    if type_aide == 'pourcentage' and taux_aide > 100:
        taux_aide = 100

    assurances_data = {
        'principale': {
            'nom': data.get('assurance_nom', 'Assurance'),
            'taux': taux_assurance,
            'montant_prise_en_charge': prise_en_charge,
        },
        'complementaire': {
            'nom': assurance2_nom,
            'taux': taux_assurance2,
            'montant_prise_en_charge': prise_en_charge2,
            'taux_modifie': data.get('taux_temp_modifie', False),
            'taux_original': data.get('taux_original', 0),
        } if assurance2_nom and taux_assurance2 > 0 else None
    }

    vente_uuid = str(uuid_module.uuid4())
    numero_local = _prochain_numero_local_offline()
    horodatage = _maintenant()
    vendeur = nom_utilisateur()

    valeurs = {
        'uuid': vente_uuid,
        'patient_uuid': patient_uuid,
        'patient_nom': data.get('patient_nom', 'Patient'),
        'structure_id': OFFLINE_STRUCTURE_ID,
        'type': type_vente,
        'sous_total': float(data.get('sous_total') or 0),
        'prise_en_charge': prise_en_charge,
        'prise_en_charge2': prise_en_charge2,
        'net_a_payer': float(data.get('net_a_payer') or 0),
        'mode_paiement': data.get('mode_paiement', 'especes'),
        'taux_assurance': taux_assurance,
        'assurance2_nom': assurance2_nom,
        'taux_assurance2': taux_assurance2,
        'societe_assurance2': societe_assurance2,
        'montant_donne': montant_donne,
        'rendu': rendu,
        'base_remboursement': base_remboursement,
        'reste_a_payer': reste_a_payer,
        'taux_temp_modifie': 1 if data.get('taux_temp_modifie') else 0,
        'taux_original': data.get('taux_original', 0),
        'assurance_principale_active': 1 if data.get('assurance_principale_active', True) else 0,
        'taux_aide': taux_aide,
        'aide_hospitaliere': float(data.get('aide_hospitaliere') or 0),
        'type_aide': type_aide,
        'applique_pbr_cac': 1 if data.get('applique_pbr_cac', True) else 0,
        'pbr_cac_variante': data.get('pbr_cac_variante') or 'defaut',
        'applique_tva': 1 if data.get('applique_tva', False) else 0,
        'numero_local': numero_local,
        colonne_articles: json.dumps(articles, ensure_ascii=False),
        'assurances': json.dumps(assurances_data, ensure_ascii=False),
        'created_by_nom': vendeur,
        'date_vente': horodatage,
    }

    insert_vente_sql = f"""
        INSERT INTO offline_ventes ({', '.join(valeurs.keys())})
        VALUES ({', '.join('?' for _ in valeurs)})
    """

    # Une vente créée pour un patient LUI AUSSI créé hors-ligne (donc
    # patient['neon_id'] encore NULL) dépend du push de ce patient d'abord
    # — outbox.push_pending() respecte cet ordre via depends_on_uuid.
    depend_de = patient_uuid if patient['neon_id'] is None else None

    payload = dict(valeurs)
    payload[colonne_articles] = articles  # objet, pas la version JSON-texte
    payload['assurances'] = assurances_data
    payload['sync_uuid'] = vente_uuid
    payload['patient_uuid'] = patient_uuid  # résolu en id Neon au push

    insert_outbox_sql = """
        INSERT INTO offline_outbox (entity_type, entity_uuid, depends_on_uuid, payload, status, created_at)
        VALUES ('vente', ?, ?, ?, 'pending', ?)
    """

    executer_plusieurs([
        (insert_vente_sql, tuple(valeurs.values())),
        (insert_outbox_sql, (vente_uuid, depend_de, json.dumps(payload, ensure_ascii=False), horodatage)),
    ])

    return {'uuid': vente_uuid, 'numero_local': numero_local}, None


@bp_ventes.route('/api/offline/ventes/actes', methods=['POST'])
def creer_vente_acte():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    data = request.json or {}
    resultat, erreur = _creer_vente(data, 'actes', 'actes')
    if erreur:
        return jsonify({'success': False, 'error': erreur[0]}), erreur[1]
    return jsonify({'success': True, **resultat})


@bp_ventes.route('/api/offline/ventes/pharma', methods=['POST'])
def creer_vente_pharma():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    data = request.json or {}
    resultat, erreur = _creer_vente(data, 'pharmacie', 'produits')
    if erreur:
        return jsonify({'success': False, 'error': erreur[0]}), erreur[1]
    return jsonify({'success': True, **resultat, 'avertissement': 'Stock non vérifié (hors-ligne) — vérifiez visuellement la disponibilité.'})
