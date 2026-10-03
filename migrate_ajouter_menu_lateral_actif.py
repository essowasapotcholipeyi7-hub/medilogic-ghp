"""Migration ponctuelle : ajoute la colonne "menu_lateral_actif" à
parametrage_affichage_structure (voir models.py) — interrupteur
SUPERADMIN par structure pour réafficher le menu latéral (en plus du
menu horizontal), patron : structure 12 le veut, d'autres non.

Additive et idempotente (ADD COLUMN IF NOT EXISTS) : aucune donnée
existante touchée, sans risque à relancer par erreur.

Usage :
    python migrate_ajouter_menu_lateral_actif.py
"""
import io
import os
import sys

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from app import app
from models import db

with app.app_context():
    db.session.execute(db.text(
        'ALTER TABLE parametrage_affichage_structure '
        'ADD COLUMN IF NOT EXISTS menu_lateral_actif BOOLEAN NOT NULL DEFAULT FALSE'
    ))
    db.session.commit()
    print('OK : colonne "menu_lateral_actif" présente sur parametrage_affichage_structure.')
