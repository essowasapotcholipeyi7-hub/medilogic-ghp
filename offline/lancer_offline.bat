@echo off
REM offline/lancer_offline.bat
REM Lance l'appli hors-ligne locale — a placer dans une tache planifiee
REM Windows ("Executer a la connexion"). Voir le plan pour l'installation
REM complete chez un client (variables d'environnement necessaires ci-dessous).
REM
REM Variables a definir sur CE PC avant le premier lancement (Panneau de
REM configuration > Variables d'environnement, ou via "setx") :
REM   OFFLINE_STRUCTURE_ID   - identifiant de la structure servie par ce PC
REM   PATIENT_ENCRYPTION_KEY - meme cle que la production (chiffrement patients)
REM   DATABASE_URL           - meme URL Neon que la production
REM   SPREADSHEET_ID         - meme feuille Google Sheets que la production
REM   ONLINE_APP_URL         - URL publique de l'appli en ligne (optionnel,
REM                            defaut https://medilogic-ghp.onrender.com)

cd /d %~dp0..
call venv\Scripts\activate.bat
python -m waitress --listen=127.0.0.1:5100 offline.app_offline:app
