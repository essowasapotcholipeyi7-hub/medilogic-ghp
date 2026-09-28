# offline/connectivity.py
"""Détection de la joignabilité de l'appli en ligne — décide la bascule.

Deux vérifications, dans cet ordre : (1) l'URL publique de l'appli répond
(c'est elle que le personnel doit utiliser dès que possible), (2) à défaut,
Neon lui-même répond (permettrait quand même de pousser la file d'attente
même si, par exemple, seul Render est en carafe et pas la base) — mais pour
la décision de BASCULE de l'interface (rediriger le personnel ou pas), seule
la joignabilité de l'appli en ligne compte : inutile de renvoyer le
personnel vers une appli en ligne qui répond mal.
"""

import socket
import urllib.request
import urllib.error

from offline.config_offline import ONLINE_APP_URL, OFFLINE_FORCE, DATABASE_URL


def app_en_ligne_joignable(timeout=6):
    if OFFLINE_FORCE:
        return False
    try:
        req = urllib.request.Request(ONLINE_APP_URL, method='GET', headers={'User-Agent': 'offline-pilot-healthcheck'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, socket.timeout, OSError):
        return False


def neon_joignable(timeout=6):
    """Test bas niveau (pas de vraie requête SQL) — juste de quoi savoir si
    la base répond, utilisé par push_pending() avant de s'y connecter pour
    de bon. Même esprit que db_failover.is_neon_reachable(), version
    allégée : une connexion psycopg2 courte suffit."""
    if OFFLINE_FORCE:
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=timeout)
        conn.close()
        return True
    except Exception:
        return False
