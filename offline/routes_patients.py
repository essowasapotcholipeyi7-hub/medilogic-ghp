# offline/routes_patients.py
"""Recherche + création de patient hors-ligne.

Recherche : même principe que api_recherche_globale() (app.py:2048-2191) —
nom/prenom/telephone sont chiffrés, donc on ne peut pas filtrer en SQL
(SQLite ne connaît pas la clé de déchiffrement). On charge tous les
patients de cette structure (un seul poste, volume forcément limité) et on
filtre en mémoire après déchiffrement.

Création : mêmes champs que l'INSERT réel (api_add_patient, app.py:2306-
2335), même chiffrement (crypto_helper.chiffrer), mais vers offline_patients
au lieu de Neon, avec un uuid généré ici et une ligne offline_outbox jumelle
dans la MÊME transaction SQLite (jamais l'une sans l'autre)."""

import json
import uuid as uuid_module
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, session

from crypto_helper import chiffrer, dechiffrer
from offline.db_offline import requeter, executer_plusieurs
from offline.config_offline import OFFLINE_STRUCTURE_ID
from offline.auth_offline import utilisateur_connecte, nom_utilisateur

bp_patients = Blueprint('offline_patients', __name__)


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _prochain_numero_local_offline():
    """Numérotation locale propre à ce pilote, repartant du dernier numéro
    connu sur Neon pour cette structure (numero_local_depart_patients,
    rafraîchi périodiquement — voir catalog_sync.rafraichir_numeros_locaux)
    — jamais de zéro, sinon collision garantie avec les patients déjà
    existants dès la 1ère création hors-ligne. Petit risque résiduel
    accepté (voir le plan) : si quelqu'un crée un patient EN LIGNE pour
    cette même structure PENDANT la coupure, depuis un autre poste."""
    depart = requeter(
        "SELECT numero_local_depart_patients AS d FROM offline_sync_state WHERE id = 1"
    )
    depart_val = depart[0]['d'] if depart else 0
    local_max = requeter(
        "SELECT COALESCE(MAX(numero_local), 0) AS m FROM offline_patients WHERE structure_id = ?",
        (OFFLINE_STRUCTURE_ID,)
    )
    local_max_val = local_max[0]['m'] if local_max else 0
    return max(depart_val, local_max_val) + 1


@bp_patients.route('/api/offline/patients/recherche')
def rechercher_patients():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401

    terme = (request.args.get('q') or '').strip().lower()
    # ⭐ ?uuid= : un patient précis (bouton « Vendre » de la liste des
    # patients → /ventes?patient=<uuid>, qui le présélectionne). Patron,
    # 2026-10-05 : avant, arrivé sur la vente, il fallait rechercher à
    # nouveau le patient sur lequel on était déjà.
    uuid_demande = (request.args.get('uuid') or '').strip()
    if uuid_demande:
        lignes = requeter(
            "SELECT * FROM offline_patients WHERE structure_id = ? AND uuid = ?",
            (OFFLINE_STRUCTURE_ID, uuid_demande)
        )
        terme = ''
    else:
        lignes = requeter(
            "SELECT * FROM offline_patients WHERE structure_id = ? ORDER BY created_at DESC",
            (OFFLINE_STRUCTURE_ID,)
        )

    resultats = []
    for ligne in lignes:
        nom = dechiffrer(ligne['nom']) or ''
        prenom = dechiffrer(ligne['prenom']) or ''
        telephone = dechiffrer(ligne['telephone']) or ''
        if terme and terme not in f"{nom} {prenom} {telephone}".lower():
            continue
        resultats.append({
            'uuid': ligne['uuid'],
            'neon_id': ligne['neon_id'],
            'nom': nom,
            'prenom': prenom,
            'telephone': telephone,
            'numero_local': ligne['numero_local'],
            'type_assurance': ligne['type_assurance'],
            'taux_prise_charge': ligne['taux_prise_charge'],
            'numero_assure': ligne['numero_assure'],
            'assurance2_nom': ligne['assurance2_nom'],
            'taux_assurance2': ligne['taux_assurance2'],
            'numero_assure2': ligne['numero_assure2'],
            'societe_assurance2': ligne['societe_assurance2'],
        })
    return jsonify({'success': True, 'patients': resultats})


@bp_patients.route('/api/offline/patients', methods=['POST'])
def creer_patient():
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401

    data = request.json or {}
    if not (data.get('nom') or '').strip():
        return jsonify({'success': False, 'error': 'Le nom est obligatoire'}), 400

    type_assurance = data.get('type_assurance', 'non_assure')
    if type_assurance and type_assurance != 'non_assure' and not (data.get('numero_assure') or '').strip():
        return jsonify({'success': False, 'error': "Le numéro d'assuré est obligatoire pour l'assurance sélectionnée."}), 400

    assurance2_nom = (data.get('assurance2_nom') or '').strip()
    if assurance2_nom and not (data.get('societe_assurance2') or '').strip():
        return jsonify({'success': False, 'error': f'Veuillez préciser la société ayant souscrit l\'assurance complémentaire "{assurance2_nom}".'}), 400

    # ⭐ Défense en profondeur (même principe qu'ailleurs dans ce dépôt) :
    # les taux par défaut sont déjà posés côté JS, revérifiés ici au cas où
    # l'appel arrive directement sans passer par le formulaire.
    taux_prise_charge = data.get('taux_prise_charge', 0) or 0
    if type_assurance != 'non_assure' and not taux_prise_charge:
        taux_prise_charge = 80
    taux_assurance2 = data.get('taux_assurance2', 0) or 0
    if assurance2_nom and not taux_assurance2:
        taux_assurance2 = 80

    patient_uuid = str(uuid_module.uuid4())
    numero_local = _prochain_numero_local_offline()
    horodatage = _maintenant()
    vendeur = nom_utilisateur()

    # Champs déjà chiffrés AVANT stockage local — pas seulement au moment
    # du push vers Neon : le fichier SQLite lui-même ne doit jamais
    # contenir de nom/prénom/téléphone en clair (même règle qu'en ligne).
    valeurs = {
        'uuid': patient_uuid,
        'structure_id': OFFLINE_STRUCTURE_ID,
        'nom': chiffrer(data.get('nom')),
        'prenom': chiffrer(data.get('prenom', '')),
        'telephone': chiffrer(data.get('telephone')),
        'adresse': data.get('adresse', ''),
        'date_naissance': data.get('date_naissance') or None,
        'type_assurance': type_assurance,
        'taux_prise_charge': taux_prise_charge,
        'numero_assure': data.get('numero_assure', ''),
        'assurance2_nom': assurance2_nom or None,
        'taux_assurance2': taux_assurance2,
        'numero_assure2': data.get('numero_assure2'),
        'societe_assurance2': data.get('societe_assurance2'),
        'personne_a_prevenir_nom': data.get('personne_a_prevenir_nom'),
        'personne_a_prevenir_telephone': data.get('personne_a_prevenir_telephone'),
        'personne_a_prevenir_relation': data.get('personne_a_prevenir_relation'),
        'email': (data.get('email') or '').strip() or None,
        'numero_local': numero_local,
        'created_by_nom': vendeur,
        'created_at': horodatage,
    }

    insert_patient_sql = f"""
        INSERT INTO offline_patients ({', '.join(valeurs.keys())})
        VALUES ({', '.join('?' for _ in valeurs)})
    """

    # Le payload de l'outbox garde nom/prenom/telephone EN CLAIR (pas la
    # version déjà chiffrée avec la clé locale) : c'est outbox.py, au
    # moment du push, qui rechiffre avec chiffrer() dans le contexte de
    # l'appli principale — évite tout risque de double-chiffrement si la
    # clé venait à changer entre-temps.
    payload = {
        'structure_id': OFFLINE_STRUCTURE_ID,
        'nom': data.get('nom'),
        'prenom': data.get('prenom', ''),
        'telephone': data.get('telephone'),
        'adresse': data.get('adresse', ''),
        'date_naissance': data.get('date_naissance') or None,
        'type_assurance': type_assurance,
        'taux_prise_charge': taux_prise_charge,
        'numero_assure': data.get('numero_assure', ''),
        'assurance2_nom': assurance2_nom or None,
        'taux_assurance2': taux_assurance2,
        'numero_assure2': data.get('numero_assure2'),
        'societe_assurance2': data.get('societe_assurance2'),
        'personne_a_prevenir_nom': data.get('personne_a_prevenir_nom'),
        'personne_a_prevenir_telephone': data.get('personne_a_prevenir_telephone'),
        'personne_a_prevenir_relation': data.get('personne_a_prevenir_relation'),
        'email': valeurs['email'],
        'numero_local': numero_local,
        'created_by_nom': vendeur,
        'sync_uuid': patient_uuid,
    }

    insert_outbox_sql = """
        INSERT INTO offline_outbox (entity_type, entity_uuid, payload, status, created_at)
        VALUES ('patient', ?, ?, 'pending', ?)
    """

    executer_plusieurs([
        (insert_patient_sql, tuple(valeurs.values())),
        (insert_outbox_sql, (patient_uuid, json.dumps(payload, ensure_ascii=False), horodatage)),
    ])

    return jsonify({'success': True, 'uuid': patient_uuid, 'numero_local': numero_local})


@bp_patients.route('/api/offline/patients/compagnies-complementaires')
def compagnies_complementaires():
    """Suggestions pour le champ assurance2_nom — même principe que
    /api/compagnies-complementaires en ligne (app.py:2221-2267) : pas une
    liste figée, juste les noms déjà rencontrés pour cette structure
    (patients déjà en cache, existants ou créés hors-ligne)."""
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    lignes = requeter(
        """SELECT DISTINCT assurance2_nom FROM offline_patients
           WHERE structure_id = ? AND assurance2_nom IS NOT NULL AND assurance2_nom != ''
           ORDER BY assurance2_nom""",
        (OFFLINE_STRUCTURE_ID,)
    )
    return jsonify({'success': True, 'items': [l['assurance2_nom'] for l in lignes]})


@bp_patients.route('/api/offline/patients/societes-assurance')
def societes_assurance():
    """Suggestions pour societe_assurance2, filtrées par le nom d'assurance
    complémentaire déjà saisi — même principe que /api/societes-assurance
    en ligne (app.py:2286-2305)."""
    if not utilisateur_connecte():
        return jsonify({'success': False, 'error': 'Non connecté'}), 401
    assurance_nom = (request.args.get('assurance') or '').strip()
    if not assurance_nom:
        return jsonify({'success': True, 'items': []})
    lignes = requeter(
        """SELECT DISTINCT societe_assurance2 FROM offline_patients
           WHERE structure_id = ? AND assurance2_nom = ?
                 AND societe_assurance2 IS NOT NULL AND societe_assurance2 != ''
           ORDER BY societe_assurance2""",
        (OFFLINE_STRUCTURE_ID, assurance_nom)
    )
    return jsonify({'success': True, 'items': [l['societe_assurance2'] for l in lignes]})
