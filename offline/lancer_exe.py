# offline/lancer_exe.py
"""Point d'entrée de l'EXÉCUTABLE Windows du mode hors-ligne
(MediLogicOffline.exe, construit par offline/exe/construire_exe.bat avec
PyInstaller). Remplace « python -m waitress ... offline.app_offline:app »
sur un PC client où l'on ne veut PAS installer Python : l'exécutable
embarque Python, Flask, waitress, psycopg2, gspread, cryptography et les
gabarits HTML du dossier offline/templates.

À côté de l'exécutable, le client ne dépose que DEUX fichiers :
  - .env               (DATABASE_URL, SPREADSHEET_ID, PATIENT_ENCRYPTION_KEY,
                        OFFLINE_STRUCTURE_ID, ONLINE_APP_URL, ...)
  - credentials.json   (compte de service Google Sheets)

Tout ce qui suit est volontairement AVANT l'import de l'appli : config.py
lit les variables d'environnement au moment de son import, donc le .env
doit déjà être chargé, et sheets_helper lit « credentials.json » relatif au
répertoire courant, donc on se place dans le dossier de l'exécutable.

Lancement direct (sans PyInstaller, pour tester le même chemin) :
    python offline/lancer_exe.py
"""
import io
import os
import sys
import time
import traceback



def dossier_application():
    """Dossier où vivent .env et credentials.json : celui de l'exécutable
    quand on est « gelé » par PyInstaller, sinon la racine du dépôt."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Tee(io.TextIOBase):
    """Écrit à la fois dans la console (fenêtre noire) et dans un fichier
    journal : la fenêtre est réduite au démarrage automatique, le journal
    est ce qu'on lira pour comprendre un problème après coup."""

    def __init__(self, console, fichier):
        self._console, self._fichier = console, fichier

    def write(self, s):
        for flux in (self._console, self._fichier):
            try:
                flux.write(s)
                flux.flush()
            except Exception:
                pass
        return len(s)

    def flush(self):
        for flux in (self._console, self._fichier):
            try:
                flux.flush()
            except Exception:
                pass

    @property
    def encoding(self):
        return 'utf-8'


def _ouvrir_journal():
    dossier = os.path.dirname(os.environ.get('OFFLINE_DB_PATH', r'C:\ProgramData\MediLogicOffline\offline.sqlite3'))
    try:
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, 'MediLogicOffline.log')
        # Journal borné : repart de zéro au-delà de ~5 Mo pour ne jamais
        # remplir le disque d'un poste qui tourne des mois sans surveillance.
        mode = 'a' if (not os.path.exists(chemin) or os.path.getsize(chemin) < 5_000_000) else 'w'
        fichier = open(chemin, mode, encoding='utf-8', errors='replace')
    except Exception as e:  # disque en lecture seule, etc.
        print(f'[offline] Journal impossible ({e}) : sortie console uniquement.')
        return None
    console = sys.stdout
    if console is not None and getattr(console, 'buffer', None) is not None:
        console = io.TextIOWrapper(console.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stdout = sys.stderr = _Tee(console, fichier)
    print(f'[offline] Journal : {chemin}')
    return chemin


def _attendre_fermeture(message):
    """Au démarrage automatique personne ne lit la fenêtre : on affiche,
    on attend, et la boucle du .bat relancera. Lancé à la main (double-
    clic), l'opérateur a le temps de lire avant que la fenêtre se ferme."""
    print('\n' + '=' * 70 + f'\n{message}\n' + '=' * 70)
    print('Fermeture dans 60 secondes (ou fermez cette fenêtre).')
    time.sleep(60)


def verifier_prerequis(dossier):
    """Messages d'erreur en français clair, pensés pour la personne qui
    installe chez le client (pas pour un développeur)."""
    env = os.path.join(dossier, '.env')
    if not os.path.exists(env):
        return (f"Fichier .env introuvable dans {dossier}\n"
                "Créez-le à côté de MediLogicOffline.exe (modèle : env.exemple, à renommer en .env).")
    manquantes = [v for v in ('DATABASE_URL', 'SPREADSHEET_ID', 'PATIENT_ENCRYPTION_KEY', 'OFFLINE_STRUCTURE_ID')
                  if not os.environ.get(v)]
    if manquantes:
        return ("Variables manquantes dans le fichier .env : " + ', '.join(manquantes) + "\n"
                "Copiez-les EXACTEMENT depuis Render (service GHP > Environment) ; "
                "OFFLINE_STRUCTURE_ID = numéro de la structure servie par CE PC.")
    if not os.path.exists(os.path.join(dossier, 'credentials.json')):
        print(f"[offline] AVERTISSEMENT : credentials.json absent de {dossier} — sans lui, le catalogue "
              "actes/médicaments et les comptes utilisateurs ne seront JAMAIS rafraîchis depuis Google "
              "Sheets, et personne ne pourra se connecter sur une première installation. L'appli démarre "
              "quand même (dernier catalogue connu) : déposez le fichier puis relancez.")
    return None


def main():
    dossier = dossier_application()
    os.chdir(dossier)  # credentials.json est lu en chemin relatif (sheets_helper)
    from dotenv import load_dotenv
    load_dotenv(os.path.join(dossier, '.env'), override=False)
    # Lu APRÈS le .env (OFFLINE_PORT peut y être défini) — 5100 par défaut.
    ecoute = f"127.0.0.1:{int(os.environ.get('OFFLINE_PORT', '5100'))}"
    _ouvrir_journal()
    print(f"[offline] MediLogicOffline — dossier : {dossier} — structure : {os.environ.get('OFFLINE_STRUCTURE_ID')}")

    erreur = verifier_prerequis(dossier)
    if erreur:
        _attendre_fermeture(erreur)
        return 2

    try:
        from offline.app_offline import app
        from waitress import serve
    except Exception:
        traceback.print_exc()
        _attendre_fermeture("L'application hors-ligne n'a pas pu démarrer (détail ci-dessus et dans le journal).")
        return 1

    while True:
        try:
            print(f'[offline] En écoute sur http://{ecoute}/ — fermez cette fenêtre pour arrêter.')
            serve(app, listen=ecoute, threads=6)
            return 0
        except OSError as e:
            # Port déjà pris : le plus souvent une AUTRE instance tourne déjà
            # (double démarrage) — on insiste doucement au lieu de planter.
            print(f"[offline] Impossible d'écouter sur {ecoute} ({e}) — nouvel essai dans 30 s. "
                  "Une autre instance tourne peut-être déjà.")
            time.sleep(30)
        except Exception:
            traceback.print_exc()
            print("[offline] Le serveur s'est arrêté — relance dans 5 s.")
            time.sleep(5)


if __name__ == '__main__':
    sys.exit(main())
