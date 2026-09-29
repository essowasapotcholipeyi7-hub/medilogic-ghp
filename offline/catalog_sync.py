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


def _valeur_sqlite(v):
    """SQLite (module sqlite3) ne sait lier que None/int/float/str/bytes —
    psycopg2 renvoie les colonnes Postgres NUMERIC/DECIMAL en
    decimal.Decimal (même quand le modèle SQLAlchemy déclare Float — dérive
    de schéma déjà vue ailleurs dans ce dépôt) et les dates en
    date/datetime : converties ici plutôt que de faire confiance au type
    déclaré côté modèle."""
    from decimal import Decimal
    from datetime import date, datetime as dt
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt, date)):
        return v.isoformat()
    return v


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


def rafraichir_patients_existants():
    """Met en cache localement les patients DÉJÀ existants de cette
    structure (créés avant l'installation du pilote, ou en ligne depuis)
    — sans ça, la recherche hors-ligne (routes_patients.rechercher_patients)
    ne trouverait QUE les patients créés pendant la coupure elle-même,
    jamais ceux déjà suivis par la clinique (bug vécu : "les patients ne
    viennent pas" au premier essai réel).

    nom/prenom/telephone restent stockés CHIFFRÉS (tels que lus depuis
    Neon) — jamais déchiffrés avant stockage local, exactement comme pour
    un patient créé hors-ligne ; déchiffrés seulement à l'affichage.

    N'ajoute que les patients pas encore en cache (déduplication par
    neon_id) — ne met PAS à jour un patient déjà caché si ses informations
    ont changé en ligne depuis : simplification acceptée pour ce pilote
    (l'essentiel — pouvoir retrouver et vendre à un patient existant
    pendant une coupure — fonctionne ; une mise à jour de champ pendant
    que ce PC était hors service resynchronisera au prochain rafraîchissement
    seulement pour les patients pas encore mis en cache)."""
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    import uuid as uuid_module
    import psycopg2
    import psycopg2.extras

    conn = get_connection()
    deja_caches = {
        row['neon_id'] for row in
        conn.execute("SELECT neon_id FROM offline_patients WHERE neon_id IS NOT NULL")
    }

    conn_pg = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    try:
        with conn_pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nom, prenom, telephone, adresse, date_naissance, type_assurance,
                       taux_prise_charge, numero_assure, assurance2_nom, taux_assurance2,
                       numero_assure2, societe_assurance2, personne_a_prevenir_nom,
                       personne_a_prevenir_telephone, personne_a_prevenir_relation, email,
                       numero_local, created_at
                FROM patients WHERE structure_id = %s
            """, (OFFLINE_STRUCTURE_ID,))
            lignes = cur.fetchall()
    finally:
        conn_pg.close()

    horodatage = _maintenant()
    n = 0
    for ligne in lignes:
        if ligne['id'] in deja_caches:
            continue
        conn.execute("""
            INSERT INTO offline_patients (
                uuid, neon_id, structure_id, nom, prenom, telephone, adresse, date_naissance,
                type_assurance, taux_prise_charge, numero_assure, assurance2_nom,
                taux_assurance2, numero_assure2, societe_assurance2, personne_a_prevenir_nom,
                personne_a_prevenir_telephone, personne_a_prevenir_relation, email,
                numero_local, created_at, synced_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, tuple(_valeur_sqlite(v) for v in (
            str(uuid_module.uuid4()), ligne['id'], OFFLINE_STRUCTURE_ID,
            ligne['nom'], ligne['prenom'], ligne['telephone'], ligne['adresse'],
            ligne['date_naissance'],
            ligne['type_assurance'], ligne['taux_prise_charge'], ligne['numero_assure'],
            ligne['assurance2_nom'], ligne['taux_assurance2'], ligne['numero_assure2'],
            ligne['societe_assurance2'], ligne['personne_a_prevenir_nom'],
            ligne['personne_a_prevenir_telephone'], ligne['personne_a_prevenir_relation'],
            ligne['email'], ligne['numero_local'],
            ligne['created_at'] or horodatage,
            horodatage,
        )))
        n += 1
    conn.commit()
    return n


def rafraichir_pbr_complementaires():
    """Cache la table des plafonds de prise en charge complémentaire (CAC)
    par acte/produit et par compagnie — voir models.py:2349-2365
    (PbrComplementaire). Sans ce cache, la vente hors-ligne ne pourrait pas
    appliquer le plafond par compagnie et sur-évaluerait la part payée par
    l'assurance complémentaire — risque réel de rejet de remboursement."""
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    import psycopg2
    import psycopg2.extras
    conn_pg = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    try:
        with conn_pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT type, nom_acte, compagnie, pbr_1, pbr_2 FROM pbr_complementaires WHERE structure_id = %s",
                (OFFLINE_STRUCTURE_ID,)
            )
            lignes = cur.fetchall()
    finally:
        conn_pg.close()

    conn = get_connection()
    conn.execute("DELETE FROM catalogue_pbr_complementaires")
    for ligne in lignes:
        conn.execute(
            """INSERT OR REPLACE INTO catalogue_pbr_complementaires (type, nom_acte, compagnie, pbr_1, pbr_2)
               VALUES (?, ?, ?, ?, ?)""",
            tuple(_valeur_sqlite(v) for v in (
                ligne['type'], ligne['nom_acte'], ligne['compagnie'], ligne['pbr_1'], ligne['pbr_2']
            ))
        )
    conn.commit()
    return len(lignes)


def rafraichir_structure_info():
    """Cache le nom/adresse/téléphone de cette structure — nécessaire pour
    l'en-tête du reçu imprimé hors-ligne (offline_recu.html), qui ne peut
    pas interroger Google Sheets/Neon en direct comme le fait la vraie
    page recu_client.html."""
    if OFFLINE_FORCE:
        raise ReseauSimuleCoupe()
    import psycopg2
    import psycopg2.extras
    conn_pg = psycopg2.connect(DATABASE_URL, connect_timeout=6)
    try:
        with conn_pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT nom, adresse, telephone, email FROM structures WHERE id = %s",
                (OFFLINE_STRUCTURE_ID,)
            )
            ligne = cur.fetchone()
    finally:
        conn_pg.close()
    if not ligne:
        return

    conn = get_connection()
    conn.execute(
        """INSERT INTO offline_structure_info (id, nom, adresse, telephone, email, refreshed_at)
           VALUES (1, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET nom=excluded.nom, adresse=excluded.adresse,
               telephone=excluded.telephone, email=excluded.email, refreshed_at=excluded.refreshed_at""",
        (ligne['nom'], ligne['adresse'], ligne['telephone'], ligne['email'], _maintenant())
    )
    conn.commit()


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
