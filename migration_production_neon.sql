-- ============================================================
-- MIGRATION PRODUCTION (Neon) — Comptabilité SYSCOHADA + Paie RH
-- ============================================================
-- Script idempotent : peut être relancé sans risque si une partie a déjà
-- été appliquée. Aucun DROP, aucune suppression de données.
-- Faites une sauvegarde (branche Neon ou export) avant de lancer, comme
-- toujours avant une migration de schéma.
-- ============================================================


-- ----------------------------------------------------------
-- 1) Colonnes d'automatisation sur ecritures_comptables
-- ----------------------------------------------------------
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS journal_code VARCHAR(10);
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS source_type VARCHAR(50);
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS source_id INTEGER;
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS generation_erreur TEXT;
ALTER TABLE ecritures_comptables ADD COLUMN IF NOT EXISTS generee_auto BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_ecritures_journal_code ON ecritures_comptables(journal_code);
CREATE INDEX IF NOT EXISTS idx_ecritures_source ON ecritures_comptables(source_type, source_id);


-- ----------------------------------------------------------
-- 1bis) Multi-comptes bancaires pour le rapprochement
-- ----------------------------------------------------------
ALTER TABLE releves_bancaires ADD COLUMN IF NOT EXISTS compte_id INTEGER
    REFERENCES comptes_comptables(id);
CREATE INDEX IF NOT EXISTS idx_releves_compte ON releves_bancaires(compte_id);


-- ----------------------------------------------------------
-- 2) structure_id sur permissions (cohérence multi-structure)
-- ----------------------------------------------------------
ALTER TABLE permissions ADD COLUMN IF NOT EXISTS structure_id INTEGER;

UPDATE permissions p SET structure_id = e.structure_id
FROM employes e
WHERE p.employe_id = e.id AND p.structure_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_permissions_structure ON permissions(structure_id);


-- ----------------------------------------------------------
-- 3) Paramétrage de paie (taux CNSS / INAM / IRPP, éditables)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS parametrage_paie (
    id SERIAL PRIMARY KEY,
    structure_id INTEGER NOT NULL UNIQUE,
    taux_cnss_salarial NUMERIC DEFAULT 4.0,
    taux_cnss_patronal NUMERIC DEFAULT 17.5,
    plafond_cnss NUMERIC DEFAULT 600000,
    taux_inam_salarial NUMERIC DEFAULT 3.5,
    taux_inam_patronal NUMERIC DEFAULT 3.5,
    tranches_irpp JSONB,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(100)
);


-- ----------------------------------------------------------
-- 4) Bulletins de paie
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS paies (
    id SERIAL PRIMARY KEY,
    structure_id INTEGER NOT NULL,
    employe_id INTEGER NOT NULL REFERENCES employes(id),
    annee INTEGER NOT NULL,
    mois INTEGER NOT NULL,
    salaire_base NUMERIC DEFAULT 0,
    primes NUMERIC DEFAULT 0,
    indemnites NUMERIC DEFAULT 0,
    salaire_brut NUMERIC DEFAULT 0,
    cnss_salarial NUMERIC DEFAULT 0,
    cnss_patronal NUMERIC DEFAULT 0,
    inam_salarial NUMERIC DEFAULT 0,
    inam_patronal NUMERIC DEFAULT 0,
    irpp NUMERIC DEFAULT 0,
    total_retenues NUMERIC DEFAULT 0,
    total_charges_patronales NUMERIC DEFAULT 0,
    net_a_payer NUMERIC DEFAULT 0,
    statut VARCHAR(20) DEFAULT 'brouillon',
    mode_paiement VARCHAR(50) DEFAULT 'especes',
    date_paiement DATE,
    depense_id INTEGER,
    ecriture_id INTEGER,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(employe_id, annee, mois)
);

CREATE INDEX IF NOT EXISTS idx_paies_structure ON paies(structure_id);
CREATE INDEX IF NOT EXISTS idx_paies_periode ON paies(structure_id, annee, mois);


-- ----------------------------------------------------------
-- 5) Correctif critique : séquences d'auto-incrément manquantes
-- ----------------------------------------------------------
-- Sur la base locale, depenses/factures/paiements_factures (+ proformas_lunettes,
-- même bug, sans lien avec ce chantier mais corrigé au passage) n'avaient
-- AUCUN auto-increment sur leur id (INSERT sans id explicite -> erreur). Ce
-- bloc vérifie et corrige uniquement les tables concernées, sans rien
-- changer si une séquence existe déjà (donc sans danger si la prod est saine).
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['depenses', 'factures', 'paiements_factures', 'proformas_lunettes']
    LOOP
        BEGIN
            IF pg_get_serial_sequence(tbl, 'id') IS NULL THEN
                EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I_id_seq OWNED BY %I.id', tbl, tbl);
                EXECUTE format(
                    'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I), 0) + 1, false)',
                    tbl || '_id_seq', tbl
                );
                EXECUTE format('ALTER TABLE %I ALTER COLUMN id SET DEFAULT nextval(%L)', tbl, tbl || '_id_seq');
                RAISE NOTICE 'Sequence creee pour %', tbl;
            ELSE
                RAISE NOTICE 'Sequence deja presente pour % — rien a faire', tbl;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- Ne bloque pas les autres tables (ex: probleme de propriétaire
            -- sur une table donnée) — à corriger à la main si ce message
            -- apparaît sur une table qui vous importe.
            RAISE NOTICE 'Impossible de corriger % : %', tbl, SQLERRM;
        END;
    END LOOP;
END $$;


-- ----------------------------------------------------------
-- Vérification finale (à lire après exécution)
-- ----------------------------------------------------------
SELECT table_name, column_name, column_default
FROM information_schema.columns
WHERE column_name = 'id' AND table_name IN ('depenses', 'factures', 'paiements_factures', 'proformas_lunettes')
ORDER BY table_name;
