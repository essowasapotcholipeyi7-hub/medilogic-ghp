# -*- mode: python ; coding: utf-8 -*-
# offline/exe/medilogic_offline.spec — recette PyInstaller de MediLogicOffline.exe
# (un seul fichier, console visible). Construire avec offline/exe/construire_exe.bat
# depuis la racine du dépôt.
import os

RACINE = os.path.abspath(os.path.join(SPECPATH, '..', '..'))

a = Analysis(
    [os.path.join(RACINE, 'offline', 'lancer_exe.py')],
    pathex=[RACINE],
    binaries=[],
    # Gabarits HTML : Flask les cherche dans <racine gelée>/offline/templates
    # (root_path du module offline.app_offline).
    datas=[(os.path.join(RACINE, 'offline', 'templates'), os.path.join('offline', 'templates'))],
    hiddenimports=[
        'waitress', 'psycopg2', 'psycopg2.extras',
        'gspread', 'oauth2client.service_account', 'httplib2',
        'cryptography.fernet', 'dotenv', 'sheets_helper', 'crypto_helper', 'config',
    ],
    hookspath=[],
    runtime_hooks=[],
    # Jamais embarqués : l'appli principale et ses gros paquets ne servent
    # pas au mode hors-ligne.
    excludes=['pandas', 'numpy', 'reportlab', 'pypdf', 'mammoth', 'openpyxl',
              'tkinter', 'matplotlib', 'PIL', 'webauthn', 'apscheduler',
              'googleapiclient', 'bs4'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='MediLogicOffline',
    console=True,
    upx=False,
    icon=None,
)
