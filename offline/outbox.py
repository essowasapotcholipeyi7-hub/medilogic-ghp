# offline/outbox.py
"""Rejeu vers Neon des écritures faites hors-ligne — voir le plan, section
"Synchronisation au retour du réseau" et "Découverte critique".

Principe : ne JAMAIS dupliquer la logique métier complexe déjà écrite dans
services/*.py (labo/radio, part médecin, comptabilité SYSCOHADA) — on
importe et on appelle ces fonctions réelles, dans un contexte Flask propre
à ce process (léger : juste models.db relié à Neon, PAS tout app.py — ces
modules services/ ne dépendent que de models.py, jamais de app.py lui-même,
donc pas besoin d'importer les 22 000 lignes ni de redémarrer en double le
planificateur/watchdog de l'appli principale).

Exception assumée : le décrément de stock Google Sheets
(_decrementer_stock_produit, app.py:7947) N'EST PAS importé tel quel — il
est défini dans app.py et dépend de db.session/db.execute_query câblés sur
CE process-là. Reproduit ici fidèlement (même verrou consultatif Postgres,
même clamp à 0, même journalisation mouvements_stock) plutôt qu'importé —
seule vraie duplication assumée de ce module, documentée comme telle.
"""

import json
import hashlib
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from crypto_helper import chiffrer
from offline.db_offline import get_connection
from offline.config_offline import DATABASE_URL, OFFLINE_STRUCTURE_ID

_flask_app = None


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _get_flask_app():
    """Contexte Flask minimal, lié à Neon — suffisant pour que
    services/*.py (qui n'utilisent que models.db) fonctionnent, sans
    importer app.py en entier. Créé une seule fois par process."""
    global _flask_app
    if _flask_app is not None:
        return _flask_app

    from flask import Flask
    from config import Config
    from models import db

    app = Flask('offline_sync')
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_BINDS'] = {}
    db.init_app(app)
    _flask_app = app
    return app


def _log_mouvement_stock(pg, structure_id, produit_id, produit_nom, type_mouvement,
                          delta, stock_apres, reference_id, user_nom):
    try:
        with pg.cursor() as cur:
            cur.execute("""
                INSERT INTO mouvements_stock
                    (structure_id, produit_id, produit_nom, type_mouvement,
                     quantite_delta, stock_apres, reference_type, reference_id, created_by_nom)
                VALUES (%s, %s, %s, %s, %s, %s, 'vente', %s, %s)
            """, (structure_id, str(produit_id), produit_nom, type_mouvement,
                  delta, stock_apres, reference_id, user_nom))
    except Exception as e:
        print(f"⚠️ Journalisation mouvement stock échouée (non bloquant) : {e}")


def _decrementer_stock_produit_offline(pg, worksheet, produit_id, quantite_vendue,
                                        produit_nom, structure_id, vente_id, user_nom):
    """Reproduction fidèle de _decrementer_stock_produit (app.py:7947) —
    voir l'en-tête du module pour la justification de cette duplication."""
    try:
        try:
            with pg.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (int(structure_id) % 2147483647, int(produit_id) % 2147483647)
                )
        except Exception as e_lock:
            print(f"   ⚠️ Verrou stock indisponible pour {produit_nom} (on continue) : {e_lock}")

        cell = worksheet.find(produit_id, in_column=1)
        if not cell:
            msg = f"produit ID {produit_id} ({produit_nom}) introuvable dans le stock"
            return False, msg

        row_num = cell.row
        current_row = worksheet.row_values(row_num)
        valeur_brute = current_row[5] if len(current_row) > 5 else ''
        try:
            stock_actuel = int(valeur_brute) if str(valeur_brute).strip() != '' else 0
        except (ValueError, TypeError):
            stock_actuel = 0

        nouveau_stock = stock_actuel - quantite_vendue
        if nouveau_stock < 0:
            nouveau_stock = 0

        worksheet.update_cell(row_num, 6, nouveau_stock)
        _log_mouvement_stock(pg, structure_id, produit_id, produit_nom, 'vente',
                              -quantite_vendue, nouveau_stock, vente_id, user_nom)
        return True, None
    except Exception as e:
        return False, f"échec mise à jour stock pour {produit_nom} (ID {produit_id}): {e}"


def _pousser_patient(pg, conn_sqlite, ligne):
    payload = json.loads(ligne['payload'])
    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            INSERT INTO patients (
                structure_id, nom, prenom, telephone, adresse, date_naissance,
                type_assurance, taux_prise_charge, numero_assure,
                assurance2_nom, taux_assurance2, numero_assure2, societe_assurance2,
                personne_a_prevenir_nom, personne_a_prevenir_telephone, personne_a_prevenir_relation,
                numero_local, email, created_at, sync_uuid, synced_from_offline_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), %s, NOW())
            ON CONFLICT (sync_uuid) WHERE sync_uuid IS NOT NULL DO UPDATE SET synced_from_offline_at = NOW()
            RETURNING id
        """, (
            payload['structure_id'],
            chiffrer(payload.get('nom')),
            chiffrer(payload.get('prenom', '')),
            chiffrer(payload.get('telephone')),
            payload.get('adresse', ''),
            payload.get('date_naissance'),
            payload.get('type_assurance', 'non_assure'),
            payload.get('taux_prise_charge', 0),
            payload.get('numero_assure', ''),
            payload.get('assurance2_nom'),
            payload.get('taux_assurance2', 0),
            payload.get('numero_assure2'),
            payload.get('societe_assurance2'),
            payload.get('personne_a_prevenir_nom'),
            payload.get('personne_a_prevenir_telephone'),
            payload.get('personne_a_prevenir_relation'),
            payload.get('numero_local'),
            payload.get('email'),
            payload['sync_uuid'],
        ))
        neon_id = cur.fetchone()['id']
    pg.commit()

    horodatage = _maintenant()
    conn_sqlite.execute(
        "UPDATE offline_patients SET neon_id = ?, synced_at = ? WHERE uuid = ?",
        (neon_id, horodatage, ligne['entity_uuid'])
    )
    conn_sqlite.execute(
        "UPDATE offline_outbox SET status = 'synced', synced_at = ? WHERE id = ?",
        (horodatage, ligne['id'])
    )
    conn_sqlite.commit()


def _resoudre_patient_neon_id(conn_sqlite, patient_uuid):
    ligne = conn_sqlite.execute(
        "SELECT neon_id FROM offline_patients WHERE uuid = ?", (patient_uuid,)
    ).fetchone()
    return ligne['neon_id'] if ligne else None


def _inserer_recette(pg, structure_id, vente_id, montant_effectif, source_type,
                      patient_nom, user_nom):
    if montant_effectif <= 0:
        return
    with pg.cursor() as cur:
        cur.execute("""
            INSERT INTO recettes (structure_id, montant, source, source_id, source_type,
                                   description, created_by_nom, date_recette)
            VALUES (%s, %s, 'patients', %s, %s, %s, %s, NOW())
        """, (
            structure_id, montant_effectif, vente_id, source_type,
            f"Vente #{vente_id} - {patient_nom} - Encaissé (synchronisé hors-ligne): {montant_effectif} FCFA",
            user_nom,
        ))
    pg.commit()


def _recalculer_caisse(pg, structure_id):
    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT COALESCE(SUM(montant), 0) AS total FROM recettes "
            "WHERE structure_id = %s AND (est_annulation IS NULL OR est_annulation = FALSE)",
            (structure_id,)
        )
        total_recettes = cur.fetchone()['total']
        cur.execute(
            "SELECT COALESCE(SUM(montant), 0) AS total FROM depenses WHERE structure_id = %s",
            (structure_id,)
        )
        total_depenses = cur.fetchone()['total']
        nouveau_solde = total_recettes - total_depenses
        cur.execute("""
            INSERT INTO caisse (structure_id, solde_actuel, date_mise_a_jour)
            VALUES (%s, %s, NOW())
            ON CONFLICT (structure_id) DO UPDATE SET
                solde_actuel = EXCLUDED.solde_actuel, date_mise_a_jour = NOW()
        """, (structure_id, nouveau_solde))
    pg.commit()


def _pousser_vente(pg, conn_sqlite, ligne):
    payload = json.loads(ligne['payload'])
    structure_id = payload['structure_id']
    type_vente = payload['type']  # 'actes' | 'pharmacie'
    vendeur = payload.get('created_by_nom') or 'System'

    patient_neon_id = _resoudre_patient_neon_id(conn_sqlite, payload['patient_uuid'])
    if not patient_neon_id:
        raise RuntimeError(f"Patient {payload['patient_uuid']} pas encore synchronisé — vente reportée")

    articles_champ = 'actes' if type_vente == 'actes' else 'produits'
    articles = payload.get(articles_champ) or []

    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            INSERT INTO ventes (
                patient_id, patient_nom, structure_id, type, sous_total, prise_en_charge,
                net_a_payer, mode_paiement, taux_assurance, date_vente, {articles_champ},
                created_by_nom, statut, assurances, assurance2_nom, taux_assurance2,
                societe_assurance2, prise_en_charge2, montant_donne, rendu, base_remboursement,
                reste_a_payer, taux_temp_modifie, taux_original, assurance_principale_active,
                taux_aide, aide_hospitaliere, type_aide, numero_local, applique_pbr_cac,
                pbr_cac_variante, applique_tva, sync_uuid, synced_from_offline_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), %s,%s,'validee',%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (sync_uuid) WHERE sync_uuid IS NOT NULL DO UPDATE SET synced_from_offline_at = NOW()
            RETURNING id
        """, (
            patient_neon_id, payload.get('patient_nom', 'Patient'), structure_id, type_vente,
            payload.get('sous_total', 0), payload.get('prise_en_charge', 0),
            payload.get('net_a_payer', 0), payload.get('mode_paiement', 'especes'),
            payload.get('taux_assurance', 0),
            json.dumps(articles, ensure_ascii=False),
            vendeur,
            json.dumps(payload.get('assurances') or {}, ensure_ascii=False),
            payload.get('assurance2_nom'), payload.get('taux_assurance2', 0),
            payload.get('societe_assurance2'), payload.get('prise_en_charge2', 0),
            payload.get('montant_donne', 0), payload.get('rendu', 0),
            payload.get('base_remboursement', 0), payload.get('reste_a_payer', 0),
            bool(payload.get('taux_temp_modifie')), payload.get('taux_original', 0),
            bool(payload.get('assurance_principale_active', True)),
            payload.get('taux_aide', 0), payload.get('aide_hospitaliere', 0),
            payload.get('type_aide', 'pourcentage'), payload.get('numero_local'),
            bool(payload.get('applique_pbr_cac', True)), payload.get('pbr_cac_variante', 'defaut'),
            bool(payload.get('applique_tva', False)), payload['sync_uuid'],
        ))
        vente_id = cur.fetchone()['id']
    pg.commit()

    # ---- Étapes 2-6 rejouées, identiques au flux en ligne ----
    montant_effectif = float(payload.get('montant_donne', 0)) - float(payload.get('rendu', 0))
    source_type = 'vente_acte' if type_vente == 'actes' else 'vente_pharma'
    _inserer_recette(pg, structure_id, vente_id, montant_effectif, source_type,
                      payload.get('patient_nom', 'Patient'), vendeur)

    if type_vente == 'pharmacie':
        try:
            from sheets_helper import sheets_helper
            sheets_helper.set_structure(structure_id)
            worksheet = sheets_helper.spreadsheet.worksheet(f"struct_{structure_id}_produits")
            for produit in articles:
                produit_id = str(produit.get('id'))
                quantite = int(produit.get('quantite') or 0)
                ok, err = _decrementer_stock_produit_offline(
                    pg, worksheet, produit_id, quantite, produit.get('nom', 'Inconnu'),
                    structure_id, vente_id, vendeur
                )
                if not ok:
                    print(f"⚠️ Stock non décrémenté (vente #{vente_id}) : {err}")
            sheets_helper.clear_cache(f"struct_{structure_id}_produits")
        except Exception as e:
            print(f"⚠️ Décrément de stock différé impossible (vente #{vente_id} conservée) : {e}")
    else:
        try:
            from services.laboratoire_service import creer_demandes_pour_vente, statut_paiement_depuis_montants
            from services.part_medecin_service import creer_lignes_part_medecin
            statut_paiement = statut_paiement_depuis_montants(
                payload.get('net_a_payer'), payload.get('reste_a_payer')
            )
            creer_demandes_pour_vente(
                structure_id, patient_neon_id, payload.get('patient_nom', 'Patient'),
                articles, vente_id, statut_paiement, None, vendeur,
            )
            creer_lignes_part_medecin(structure_id, articles, vente_id, vendeur)
        except Exception as e:
            print(f"⚠️ Labo/part médecin non générés (vente #{vente_id} conservée) : {e}")

    _recalculer_caisse(pg, structure_id)

    try:
        from services.comptabilite_service import generer_ecriture_vente
        from models import Vente
        vente_orm = Vente.query.get(vente_id)
        if vente_orm:
            generer_ecriture_vente(vente_orm, user_nom=vendeur)
    except Exception as e:
        print(f"⚠️ Écriture comptable non générée (vente #{vente_id} conservée) : {e}")

    horodatage = _maintenant()
    conn_sqlite.execute(
        "UPDATE offline_ventes SET neon_id = ?, synced_at = ? WHERE uuid = ?",
        (vente_id, horodatage, ligne['entity_uuid'])
    )
    conn_sqlite.execute(
        "UPDATE offline_outbox SET status = 'synced', synced_at = ? WHERE id = ?",
        (horodatage, ligne['id'])
    )
    conn_sqlite.commit()


def push_pending():
    """Rejoue toute la file d'attente vers Neon. Sûr à rappeler plusieurs
    fois de suite (les lignes déjà 'synced' sont ignorées ; ON CONFLICT
    (sync_uuid) rend chaque upsert idempotent en cas de coupure en plein
    envoi)."""
    conn_sqlite = get_connection()
    lignes = conn_sqlite.execute(
        "SELECT * FROM offline_outbox WHERE status = 'pending' ORDER BY id ASC"
    ).fetchall()

    resultats = {'synchronises': 0, 'differes': 0, 'erreurs': 0}
    if not lignes:
        return resultats

    app = _get_flask_app()
    with app.app_context():
        pg = psycopg2.connect(DATABASE_URL)
        pg.autocommit = False
        try:
            for ligne in lignes:
                if ligne['depends_on_uuid']:
                    dep = conn_sqlite.execute(
                        "SELECT status FROM offline_outbox WHERE entity_uuid = ? AND entity_type = 'patient'",
                        (ligne['depends_on_uuid'],)
                    ).fetchone()
                    if not dep or dep['status'] != 'synced':
                        resultats['differes'] += 1
                        continue
                try:
                    if ligne['entity_type'] == 'patient':
                        _pousser_patient(pg, conn_sqlite, ligne)
                    else:
                        _pousser_vente(pg, conn_sqlite, ligne)
                    resultats['synchronises'] += 1
                except Exception as e:
                    pg.rollback()
                    conn_sqlite.execute(
                        "UPDATE offline_outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                        (str(e), ligne['id'])
                    )
                    conn_sqlite.commit()
                    resultats['erreurs'] += 1
        finally:
            pg.close()

    conn_sqlite.execute(
        "UPDATE offline_sync_state SET last_successful_push_at = ? WHERE id = 1",
        (_maintenant(),)
    )
    conn_sqlite.commit()
    return resultats
