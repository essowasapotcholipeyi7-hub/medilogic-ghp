# offline/db_offline.py
"""Connexion SQLite locale — un seul fichier, pas de service à administrer.

PRAGMA journal_mode=WAL : plusieurs onglets/requêtes peuvent lire pendant
qu'une écriture est en cours (WAL = write-ahead log) — utile puisque
plusieurs onglets du navigateur pourraient être ouverts sur ce même PC.
PRAGMA foreign_keys=ON : les FK déclarées dans le schéma (voir
models_offline.py) sont réellement vérifiées (SQLite ne le fait pas par
défaut, contrairement à Postgres).
"""

import os
import sqlite3
import threading

from offline.config_offline import OFFLINE_DB_PATH

_local = threading.local()


def _ensure_parent_dir():
    parent = os.path.dirname(OFFLINE_DB_PATH)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)


def get_connection():
    """Une connexion SQLite par thread (sqlite3 n'est pas thread-safe sur une
    connexion partagée) — Flask sert chaque requête sur son propre thread
    avec le serveur de dev/waitress, donc ce pattern est suffisant ici."""
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn

    _ensure_parent_dir()
    conn = sqlite3.connect(OFFLINE_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=30000')
    _local.conn = conn
    return conn


def executer(sql, params=()):
    """INSERT/UPDATE/DELETE — commit immédiat (autocommit implicite, pas de
    grosse transaction longue vu le volume d'écritures d'un seul poste)."""
    conn = get_connection()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def executer_plusieurs(operations):
    """Plusieurs écritures dans UNE seule transaction — utilisé quand
    plusieurs tables doivent rester cohérentes entre elles (ex: créer une
    vente ET sa ligne d'outbox en même temps : jamais l'une sans l'autre).
    `operations` est une liste de (sql, params)."""
    conn = get_connection()
    try:
        for sql, params in operations:
            conn.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def requeter(sql, params=()):
    conn = get_connection()
    return conn.execute(sql, params).fetchall()


def requeter_une(sql, params=()):
    conn = get_connection()
    return conn.execute(sql, params).fetchone()
