# offline/config_offline.py
"""Configuration du pilote hors-ligne — voir
C:\\Users\\HP\\.claude\\plans\\wild-inventing-bubble.md pour le contexte
complet.

Réutilise Config (config.py, racine du dépôt) pour tout ce qui est partagé
avec l'appli principale (URL Neon, feuille Google Sheets) — n'introduit que
ce qui est propre à ce pilote : où vit le fichier SQLite local, quelle
structure ce PC sert, et l'URL publique de l'appli en ligne à surveiller.
"""

import os
from config import Config

# Chemin du fichier SQLite local. Le dossier est créé s'il n'existe pas
# (voir db_offline.py). Un seul fichier par PC — ce pilote ne sert qu'une
# seule structure par installation (voir OFFLINE_STRUCTURE_ID ci-dessous).
OFFLINE_DB_PATH = os.environ.get(
    'OFFLINE_DB_PATH',
    r'C:\ProgramData\MediLogicOffline\offline.sqlite3'
)

# ⭐ Fixée UNE FOIS à l'installation chez CE client — le code lui-même ne
# code en dur AUCUNE structure : la même appli offline/ sert n'importe
# quelle structure, seule cette variable d'environnement change d'un client
# à l'autre. Obligatoire : on refuse de démarrer sans elle (voir
# app_offline.py) plutôt que de deviner ou de servir "structure 1" par
# défaut, ce qui serait une fuite de données vers le mauvais client.
OFFLINE_STRUCTURE_ID = os.environ.get('OFFLINE_STRUCTURE_ID')

# URL publique de l'appli en ligne normale, testée pour décider de la
# bascule (voir connectivity.py). Ex: https://medilogic-ghp.onrender.com
ONLINE_APP_URL = os.environ.get('ONLINE_APP_URL', 'https://medilogic-ghp.onrender.com')

# Pour les tests : force le mode hors-ligne sans couper vraiment le réseau
# (voir connectivity.py). Ne jamais positionner en usage réel.
OFFLINE_FORCE = os.environ.get('OFFLINE_FORCE') == '1'

DATABASE_URL = Config.DATABASE_URL
SPREADSHEET_ID = Config.SPREADSHEET_ID

# Rythmes de rafraîchissement (secondes) pendant que le réseau est bon.
CATALOG_REFRESH_INTERVAL_SECONDS = int(os.environ.get('OFFLINE_CATALOG_REFRESH_SECONDS', 600))
USERS_CACHE_REFRESH_INTERVAL_SECONDS = int(os.environ.get('OFFLINE_USERS_REFRESH_SECONDS', 600))
CONNECTIVITY_CHECK_INTERVAL_SECONDS = int(os.environ.get('OFFLINE_CHECK_INTERVAL_SECONDS', 20))

# ⭐ Sauvegarde locale périodique du fichier SQLite — voir offline/backup.py.
# Tourne QUE le PC soit en ligne ou hors-ligne (c'est justement pendant une
# coupure que les ventes non encore synchronisées ont le plus besoin d'être
# protégées d'une panne du poste). OFFLINE_BACKUP_DIR est optionnelle : un
# second emplacement (clé USB branchée en permanence, lecteur réseau...) en
# plus du dossier local par défaut — utile si ce PC lui-même tombe en panne
# (le dossier local seul ne protège que contre une corruption du fichier).
BACKUP_INTERVAL_SECONDS = int(os.environ.get('OFFLINE_BACKUP_INTERVAL_SECONDS', 900))
BACKUP_RETENTION = int(os.environ.get('OFFLINE_BACKUP_RETENTION', 40))
BACKUP_DIR_SECONDAIRE = os.environ.get('OFFLINE_BACKUP_DIR')
# Comme db_failover.py : plusieurs échecs consécutifs avant de déclarer
# hors-ligne, pour ne pas basculer sur un simple hoquet réseau isolé.
SEUIL_ECHECS_AVANT_BASCULE = 2
