# offline/catalog_sync.py
"""Instantané local, lecture seule, des tarifs actes/produits de CETTE
structure — sur le modèle de utils/sheets_mirror.py, simplifié à une seule
structure (pas de boucle sur toutes les structures).

Nécessaire car le catalogue de prix normal est lu EN DIRECT depuis Google
Sheets (voir GET /actes_vente, app.py:2765-2774) — totalement injoignable
hors-ligne sans ce cache. Rafraîchi uniquement pendant que le réseau est bon
(voir watchdog_offline.py) ; jamais modifié hors-ligne (aucune création de
produit/acte en local, hors périmètre du pilote).

Cache également les identifiants du personnel de cette structure
(offline_users_cache) — même rythme de rafraîchissement, même source
(Google Sheets, feuille struct_{id}_users), pour permettre la connexion
hors-ligne (voir auth_offline.py).
"""

import json
from datetime import datetime, timezone

from sheets_helper import sheets_helper
from offline.config_offline import OFFLINE_STRUCTURE_ID, DATABASE_URL, OFFLINE_FORCE
from offline.db_offline import get_connection


class ReseauSimuleCoupe(Exception):
    """Levée quand OFFLINE_FORCE=1 — pour que les rafraîchissements se
    comportent EXACTEMENT comme en cas de vraie coupure (utilisé pour les
    tests, voir le plan § Vérification), au lieu d'atteindre Sheets/Neon
    pour de vrai malgré le mode hors-ligne simulé."""
    pass


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _rafraichir_table(nom_table, base_sheet, cle_champ):
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    sheets_helper.set_structure(OFFLINE_STRUCTURE_ID)
    lignes = sheets_helper.get_all_records(base_sheet, use_prefix=True, force_refresh=True)
    if lignes is None:
        return 0

    conn = get_connection()
    horodatage = _maintenant()
    conn.execute(f"DELETE FROM {nom_table}")
    for ligne in lignes:
        cle = str(ligne.get(cle_champ) or '').strip()
        if not cle:
            continue
        conn.execute(
            f"INSERT OR REPLACE INTO {nom_table} (nom, donnees, refreshed_at) VALUES (?, ?, ?)",
            (cle, json.dumps(ligne, ensure_ascii=False), horodatage)
        )
    conn.commit()
    return len(lignes)


def rafraichir_catalogue():
    """Retourne (nb_actes, nb_produits). Lève une exception si Sheets est
    injoignable — c'est à l'appelant (watchdog) de ne pas casser le reste
    du cycle pour autant."""
    nb_actes = _rafraichir_table('catalogue_actes', 'actes', 'nom')
    nb_produits = _rafraichir_table('catalogue_produits', 'produits', 'nom')

    conn = get_connection()
    conn.execute(
        "UPDATE offline_sync_state SET last_successful_catalog_refresh_at = ? WHERE id = 1",
        (_maintenant(),)
    )
    conn.commit()
    return nb_actes, nb_produits


def rafraichir_numeros_locaux():
    """Lit sur Neon le dernier numero_local déjà utilisé par CETTE structure
    pour patients/ventes — sert de point de départ au compteur local
    (voir routes_patients.py/routes_ventes.py), pour ne jamais réutiliser un
    numéro déjà pris par un patient/une vente existants. Sans ce
    rafraîchissement, un enregistrement créé hors-ligne sur une structure
    qui a déjà de l'historique entrerait en collision avec le tout premier
    essai (numero_local=1 déjà pris)."""
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    import psycopg2
    conn_pg = psycopg2.connect(DATABASE_URL, connect_timeout=6)
    try:
        with conn_pg.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(numero_local), 0) FROM patients WHERE structure_id = %s",
                (OFFLINE_STRUCTURE_ID,)
            )
            depart_patients = cur.fetchone()[0]
            cur.execute(
                "SELECT COALESCE(MAX(numero_local), 0) FROM ventes WHERE structure_id = %s",
                (OFFLINE_STRUCTURE_ID,)
            )
            depart_ventes = cur.fetchone()[0]
    finally:
        conn_pg.close()

    conn = get_connection()
    conn.execute(
        """UPDATE offline_sync_state
           SET numero_local_depart_patients = MAX(numero_local_depart_patients, ?),
               numero_local_depart_ventes = MAX(numero_local_depart_ventes, ?)
           WHERE id = 1""",
        (depart_patients, depart_ventes)
    )
    conn.commit()
    return depart_patients, depart_ventes


def rafraichir_utilisateurs():
    """Cache email + hash de mot de passe + rôle des comptes de cette
    structure — jamais le mot de passe en clair. Même source que la vraie
    connexion en ligne (feuille struct_{id}_users, voir index() app.py)."""
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    sheets_helper.set_structure(OFFLINE_STRUCTURE_ID)
    lignes = sheets_helper.get_all_records('users', use_prefix=True, force_refresh=True)
    if lignes is None:
        return 0

    conn = get_connection()
    horodatage = _maintenant()
    conn.execute("DELETE FROM offline_users_cache")
    n = 0
    for ligne in lignes:
        email = str(ligne.get('email') or '').strip()
        mdp_hash = ligne.get('mot_de_passe')
        if not email or not mdp_hash:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO offline_users_cache
               (email, nom, mot_de_passe_hash, role, actif, refreshed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                email,
                ligne.get('nom', ''),
                mdp_hash,
                ligne.get('role', 'caissier'),
                1 if str(ligne.get('actif', 'oui')) == 'oui' else 0,
                horodatage,
            )
        )
        n += 1
    conn.commit()

    conn.execute(
        "UPDATE offline_sync_state SET last_successful_users_refresh_at = ? WHERE id = 1",
        (horodatage,)
    )
    conn.commit()
    return n
