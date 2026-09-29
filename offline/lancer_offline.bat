@echo off
REM offline/lancer_offline.bat
REM Lance l'appli hors-ligne locale — a placer dans une tache planifiee
REM Windows ("Executer a la connexion") ou dans le dossier Demarrage. Voir
REM le plan pour l'installation complete chez un client (variables
REM d'environnement necessaires ci-dessous).
REM
REM Variables a definir sur CE PC avant le premier lancement (Panneau de
REM configuration > Variables d'environnement, ou via "setx") :
REM   OFFLINE_STRUCTURE_ID   - identifiant de la structure servie par ce PC
REM   PATIENT_ENCRYPTION_KEY - meme cle que la production (chiffrement patients)
REM   DATABASE_URL           - meme URL Neon que la production
REM   SPREADSHEET_ID         - meme feuille Google Sheets que la production
REM   ONLINE_APP_URL         - URL publique de l'appli en ligne (optionnel,
REM                            defaut https://medilogic-ghp.onrender.com)
REM
REM Redemarrage automatique : si le process s'arrete pour une raison
REM quelconque (plantage Python, coupure electrique du poste pendant que
REM Windows redemarre l'appli seule, etc.), la boucle ci-dessous le
REM relance apres une courte pause, sans intervention manuelle. Utile
REM surtout pour l'installation sans droits admin (dossier Demarrage), qui
REM n'a pas le redemarrage automatique natif d'une tache planifiee.

cd /d %~dp0..
call venv\Scripts\activate.bat

:boucle
python -m waitress --listen=127.0.0.1:5100 offline.app_offline:app
echo.
echo [%date% %time%] L'appli hors-ligne s'est arretee — relance dans 5 secondes...
timeout /t 5 /nobreak >nul
goto boucle
