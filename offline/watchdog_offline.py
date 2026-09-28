# offline/watchdog_offline.py
"""Fil de fond : surveille la connectivité, déclenche la synchro et les
rafraîchissements catalogue/utilisateurs dès que le réseau redevient bon.
Même principe que db_failover.start_watchdog() (plusieurs échecs
consécutifs avant de déclarer hors-ligne, pour éviter les faux positifs
d'un simple hoquet réseau isolé) — mécanisme réécrit ici, pas réutilisé
tel quel (celui-là est Postgres↔Postgres, sans rapport avec SQLite/UUID)."""

import threading
import time
from datetime import datetime, timezone

from offline.config_offline import (
    CONNECTIVITY_CHECK_INTERVAL_SECONDS,
    CATALOG_REFRESH_INTERVAL_SECONDS,
    USERS_CACHE_REFRESH_INTERVAL_SECONDS,
    SEUIL_ECHECS_AVANT_BASCULE,
)
from offline.connectivity import app_en_ligne_joignable
from offline.db_offline import get_connection

_demarre = False


def _maintenant():
    return datetime.now(timezone.utc).isoformat()


def _marquer_mode(mode):
    conn = get_connection()
    if mode == 'offline':
        conn.execute(
            "UPDATE offline_sync_state SET mode = ?, last_switch_to_offline_at = ? WHERE id = 1",
            (mode, _maintenant())
        )
    else:
        conn.execute("UPDATE offline_sync_state SET mode = ? WHERE id = 1", (mode,))
    conn.commit()


def _cycle():
    from offline.outbox import push_pending
    from offline.catalog_sync import rafraichir_catalogue, rafraichir_utilisateurs, rafraichir_numeros_locaux

    conn = get_connection()
    ligne = conn.execute("SELECT mode FROM offline_sync_state WHERE id = 1").fetchone()
    mode_actuel = ligne['mode'] if ligne else 'online'

    echecs_consecutifs = getattr(_cycle, '_echecs', 0)
    dernier_refresh_catalogue = getattr(_cycle, '_dernier_refresh_catalogue', 0)
    dernier_refresh_users = getattr(_cycle, '_dernier_refresh_users', 0)

    joignable = app_en_ligne_joignable()

    if mode_actuel == 'offline':
        if joignable:
            try:
                resultats = push_pending()
                print(f"[offline-watchdog] Synchronisation : {resultats}")
            except Exception as e:
                print(f"[offline-watchdog] Erreur de synchronisation : {e}")
                conn.execute(
                    "UPDATE offline_sync_state SET last_error = ?, last_error_at = ? WHERE id = 1",
                    (str(e), _maintenant())
                )
                conn.commit()
                joignable = False  # ne repasse pas en ligne si la synchro a échoué

        if joignable:
            _marquer_mode('online')
            echecs_consecutifs = 0
            print("[offline-watchdog] Retour en mode en ligne.")
    else:
        if not joignable:
            echecs_consecutifs += 1
            if echecs_consecutifs >= SEUIL_ECHECS_AVANT_BASCULE:
                _marquer_mode('offline')
                print(f"[offline-watchdog] Bascule en mode hors-ligne ({echecs_consecutifs} échecs consécutifs).")
        else:
            echecs_consecutifs = 0
            maintenant_ts = time.time()
            if maintenant_ts - dernier_refresh_catalogue > CATALOG_REFRESH_INTERVAL_SECONDS:
                try:
                    rafraichir_catalogue()
                    rafraichir_numeros_locaux()
                    dernier_refresh_catalogue = maintenant_ts
                except Exception as e:
                    print(f"[offline-watchdog] Rafraîchissement catalogue échoué : {e}")
            if maintenant_ts - dernier_refresh_users > USERS_CACHE_REFRESH_INTERVAL_SECONDS:
                try:
                    rafraichir_utilisateurs()
                    dernier_refresh_users = maintenant_ts
                except Exception as e:
                    print(f"[offline-watchdog] Rafraîchissement utilisateurs échoué : {e}")

    _cycle._echecs = echecs_consecutifs
    _cycle._dernier_refresh_catalogue = dernier_refresh_catalogue
    _cycle._dernier_refresh_users = dernier_refresh_users


def demarrer():
    global _demarre
    if _demarre:
        return
    _demarre = True

    def _boucle():
        while True:
            try:
                _cycle()
            except Exception as e:
                print(f"[offline-watchdog] Erreur inattendue dans le cycle : {e}")
            time.sleep(CONNECTIVITY_CHECK_INTERVAL_SECONDS)

    t = threading.Thread(target=_boucle, name='offline-watchdog', daemon=True)
    t.start()
    print(f"[offline-watchdog] Démarré (intervalle={CONNECTIVITY_CHECK_INTERVAL_SECONDS}s).")
