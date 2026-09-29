# offline/models_offline.py
"""Schéma SQLite local — voir le plan (§ "Ce qui est répliqué localement")
pour le détail des choix. `sqlite3` brut du stdlib, pas un second objet
SQLAlchemy : évite toute tentation de réutiliser le `db` de models.py
(câblé sur FailoverSession/Postgres, sans rapport avec ce pilote).

Toutes les tables sont créées avec CREATE TABLE IF NOT EXISTS — appeler
`initialiser_schema()` au démarrage de l'appli offline est donc toujours
sûr, y compris sur un fichier déjà initialisé.
"""

from offline.db_offline import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS offline_patients (
    uuid TEXT PRIMARY KEY,
    neon_id INTEGER,
    structure_id INTEGER NOT NULL,
    nom TEXT NOT NULL,
    prenom TEXT NOT NULL,
    telephone TEXT,
    date_naissance TEXT,
    adresse TEXT,
    type_assurance TEXT,
    taux_prise_charge REAL DEFAULT 0,
    numero_assure TEXT,
    assurance2_nom TEXT,
    taux_assurance2 REAL DEFAULT 0,
    numero_assure2 TEXT,
    societe_assurance2 TEXT,
    personne_a_prevenir_nom TEXT,
    personne_a_prevenir_telephone TEXT,
    personne_a_prevenir_relation TEXT,
    email TEXT,
    numero_local INTEGER,
    created_by_nom TEXT,
    created_at TEXT NOT NULL,
    synced_at TEXT
);

-- Un patient Neon (déjà existant, mis en cache par
-- catalog_sync.rafraichir_patients_existants) ne doit jamais être caché
-- deux fois — filet de sécurité en plus de la dédoublonnage côté Python.
CREATE UNIQUE INDEX IF NOT EXISTS ix_offline_patients_neon_id
    ON offline_patients (neon_id) WHERE neon_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS offline_ventes (
    uuid TEXT PRIMARY KEY,
    neon_id INTEGER,
    patient_uuid TEXT NOT NULL REFERENCES offline_patients(uuid),
    patient_neon_id INTEGER,
    patient_nom TEXT,
    structure_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    sous_total REAL DEFAULT 0,
    prise_en_charge REAL DEFAULT 0,
    prise_en_charge2 REAL DEFAULT 0,
    net_a_payer REAL DEFAULT 0,
    mode_paiement TEXT,
    taux_assurance REAL DEFAULT 0,
    assurance2_nom TEXT,
    taux_assurance2 REAL DEFAULT 0,
    societe_assurance2 TEXT,
    montant_donne REAL DEFAULT 0,
    rendu REAL DEFAULT 0,
    base_remboursement REAL DEFAULT 0,
    reste_a_payer REAL DEFAULT 0,
    taux_temp_modifie INTEGER DEFAULT 0,
    taux_original REAL DEFAULT 0,
    assurance_principale_active INTEGER DEFAULT 1,
    taux_aide REAL DEFAULT 0,
    aide_hospitaliere REAL DEFAULT 0,
    type_aide TEXT DEFAULT 'pourcentage',
    applique_pbr_cac INTEGER DEFAULT 1,
    pbr_cac_variante TEXT DEFAULT 'defaut',
    applique_tva INTEGER DEFAULT 0,
    numero_local INTEGER,
    actes TEXT,
    produits TEXT,
    assurances TEXT,
    statut TEXT DEFAULT 'validee',
    created_by_nom TEXT,
    date_vente TEXT NOT NULL,
    synced_at TEXT
);

CREATE TABLE IF NOT EXISTS catalogue_actes (
    nom TEXT PRIMARY KEY,
    donnees TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalogue_produits (
    nom TEXT PRIMARY KEY,
    donnees TEXT NOT NULL,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offline_users_cache (
    email TEXT PRIMARY KEY,
    nom TEXT,
    mot_de_passe_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    actif INTEGER DEFAULT 1,
    refreshed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offline_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,          -- 'patient' | 'vente'
    entity_uuid TEXT NOT NULL,
    depends_on_uuid TEXT,               -- vente créée hors-ligne pour un
                                         -- patient lui aussi créé hors-ligne
    payload TEXT NOT NULL,              -- JSON, déjà prêt pour l'INSERT Neon
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | synced | error
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    synced_at TEXT,
    last_error TEXT
);

-- Plafonds de prise en charge complémentaire (CAC) par acte/produit et par
-- compagnie d'assurance — voir pbr_complementaires côté Neon
-- (models.py:2349-2365). Indispensable pour un calcul d'assurance correct :
-- sans ça, le pilote sous-évaluait la part patient / sur-évaluait la part
-- assurance, avec un vrai risque de rejet de remboursement.
CREATE TABLE IF NOT EXISTS catalogue_pbr_complementaires (
    type TEXT NOT NULL,        -- 'acte' | 'produit'
    nom_acte TEXT NOT NULL,
    compagnie TEXT NOT NULL,
    pbr_1 REAL NOT NULL,
    pbr_2 REAL,
    PRIMARY KEY (type, nom_acte, compagnie)
);

CREATE TABLE IF NOT EXISTS offline_structure_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    nom TEXT,
    adresse TEXT,
    telephone TEXT,
    email TEXT,
    refreshed_at TEXT
);

CREATE TABLE IF NOT EXISTS offline_sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'online',   -- online | offline
    structure_id INTEGER,
    last_switch_to_offline_at TEXT,
    last_successful_push_at TEXT,
    last_successful_catalog_refresh_at TEXT,
    last_successful_users_refresh_at TEXT,
    last_error TEXT,
    last_error_at TEXT,
    -- Dernier numero_local connu côté Neon pour CETTE structure au moment du
    -- dernier rafraîchissement (voir catalog_sync.rafraichir_numeros_locaux)
    -- — sans ça, le compteur local repartirait de zéro et collisionnerait
    -- immédiatement avec les patients/ventes déjà existants de la structure.
    numero_local_depart_patients INTEGER NOT NULL DEFAULT 0,
    numero_local_depart_ventes INTEGER NOT NULL DEFAULT 0
);
"""


def initialiser_schema():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR IGNORE INTO offline_sync_state (id, mode) VALUES (1, 'online')"
    )
    conn.commit()
