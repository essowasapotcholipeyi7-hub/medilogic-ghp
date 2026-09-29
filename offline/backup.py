# offline/backup.py
"""Sauvegarde périodique du fichier SQLite local — voir
config_offline.BACKUP_INTERVAL_SECONDS / BACKUP_DIR_SECONDAIRE.

Pourquoi une sauvegarde séparée du fichier .sqlite3 lui-même : si le PC de
la clinique tombe en panne (disque mort, coupure de courant en pleine
écriture) pendant une coupure réseau, les ventes pas encore synchronisées
vers Neon n'existent QUE dans ce fichier local — les perdre reviendrait à
perdre des encaissements réels, pas de simples données de confort.

Utilise sqlite3.Connection.backup() (API native de sauvegarde à chaud), pas
une simple copie de fichier : capture un instantané cohérent même en mode
WAL avec des écritures en cours, ce qu'une copie brute de offline.sqlite3
ne garantirait pas (le journal WAL n'a peut-être pas encore été rejoué dans
le fichier principal au moment de la copie).
"""

import os
import glob
import sqlite3
from datetime import datetime, timezone

from offline.config_offline import OFFLINE_DB_PATH, BACKUP_DIR_SECONDAIRE, BACKUP_RETENTION
from offline.db_offline import get_connection

DOSSIER_LOCAL = os.path.join(os.path.dirname(OFFLINE_DB_PATH), 'backups')


def _horodatage():
    return datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')


def _copier_vers(dossier, nom_fichier):
    os.makedirs(dossier, exist_ok=True)
    destination = os.path.join(dossier, nom_fichier)
    source = get_connection()
    cible = sqlite3.connect(destination)
    try:
        source.backup(cible)
    finally:
        cible.close()
    return destination


def _purger_anciennes(dossier):
    """Ne garde que les BACKUP_RETENTION sauvegardes les plus récentes de ce
    dossier — sans ça, il grossirait indéfiniment sur un pilote qui tourne
    des mois sans jamais être nettoyé manuellement."""
    fichiers = sorted(
        glob.glob(os.path.join(dossier, 'offline_*.sqlite3')),
        key=os.path.getmtime,
        reverse=True,
    )
    for f in fichiers[BACKUP_RETENTION:]:
        try:
            os.remove(f)
        except OSError:
            pass


def sauvegarder():
    """Sauvegarde locale (toujours) + secondaire si OFFLINE_BACKUP_DIR est
    configurée (clé USB branchée en permanence, lecteur réseau...). Renvoie
    (ok, erreur_ou_None) — ok=True même si seule la secondaire a échoué : la
    copie locale reste la protection minimale garantie."""
    nom_fichier = f'offline_{_horodatage()}.sqlite3'
    try:
        _copier_vers(DOSSIER_LOCAL, nom_fichier)
        _purger_anciennes(DOSSIER_LOCAL)
    except Exception as e:
        return False, f"Sauvegarde locale échouée : {e}"

    if BACKUP_DIR_SECONDAIRE:
        try:
            _copier_vers(BACKUP_DIR_SECONDAIRE, nom_fichier)
            _purger_anciennes(BACKUP_DIR_SECONDAIRE)
        except Exception as e:
            # La copie locale a réussi — rien n'est perdu, mais le second
            # emplacement (clé USB débranchée ? dossier réseau injoignable ?)
            # n'a pas pu être atteint : à signaler, jamais à masquer.
            return True, f"Sauvegarde secondaire ({BACKUP_DIR_SECONDAIRE}) échouée : {e}"

    return True, None
