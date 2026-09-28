# scripts/ajouter_sync_uuid_offline.py
# ============================================================
# COLONNE sync_uuid — PILOTE HORS-LIGNE (offline/)
# ============================================================
# Ajoute à patients/ventes une colonne d'identité stable, générée côté
# client (UUID), utilisée UNIQUEMENT par le pilote hors-ligne (voir
# C:\Users\HP\.claude\plans\wild-inventing-bubble.md) pour resynchroniser
# vers Neon un enregistrement créé hors-ligne sans jamais entrer en
# collision avec l'id technique (séquence Postgres normale, jamais touchée
# ni prédite par le pilote — l'INSERT de synchro l'omet et laisse Postgres
# l'attribuer).
#
# NULL pour tout enregistrement créé normalement en ligne (immense majorité
# des lignes) — cette colonne ne sert qu'aux lignes qui ont transité par le
# pilote hors-ligne. `synced_from_offline_at` permet de distinguer d'un coup
# d'œil "créé hors-ligne puis synchronisé" de "créé en ligne comme d'habitude".
#
# Idempotent : peut être relancé sans danger (ADD COLUMN IF NOT EXISTS,
# index CREATE ... IF NOT EXISTS).
#
# Utilisation :
#   python scripts/ajouter_sync_uuid_offline.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from sqlalchemy import text

TABLES = ['patients', 'ventes']


def migrer():
    with app.app_context():
        for table in TABLES:
            print(f"\n=== {table} ===")

            db.session.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS sync_uuid VARCHAR(36)"
            ))
            db.session.execute(text(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS synced_from_offline_at TIMESTAMP"
            ))
            db.session.commit()
            print("  colonnes sync_uuid / synced_from_offline_at OK")

            # Index unique PARTIEL : seules les lignes réellement issues du
            # pilote hors-ligne (sync_uuid NOT NULL) sont contraintes à
            # l'unicité — les millions de lignes existantes/en ligne, toutes
            # à NULL, ne sont jamais concernées.
            db.session.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_sync_uuid
                ON {table} (sync_uuid) WHERE sync_uuid IS NOT NULL
            """))
            db.session.commit()
            print("  index unique partiel OK")

            # Vérification : la colonne existe, aucune ligne existante n'est
            # affectée (sync_uuid doit rester NULL partout tant que le
            # pilote n'a rien poussé).
            total = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            avec_uuid = db.session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE sync_uuid IS NOT NULL")
            ).scalar()
            print(f"  total={total} avec_sync_uuid={avec_uuid} (attendu: 0 avant tout usage du pilote)")


if __name__ == '__main__':
    migrer()
    print("\n✅ Migration sync_uuid (pilote hors-ligne) terminée.")
