@echo off
REM offline/installer_tache_planifiee.bat
REM A executer UNE SEULE FOIS sur le PC client, en tant qu'administrateur,
REM depuis le dossier racine du projet (C:\medilogic_ghp ou equivalent).
REM Cree une tache planifiee Windows qui lance l'appli hors-ligne a chaque
REM connexion de l'utilisateur, puis la demarre immediatement pour verifier.

setlocal
set TACHE_NOM=MediLogicOffline
set SCRIPT=%~dp0lancer_offline.bat

echo Creation de la tache planifiee "%TACHE_NOM%"...
schtasks /Create /TN "%TACHE_NOM%" /TR "\"%SCRIPT%\"" /SC ONLOGON /RL LIMITED /F

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ECHEC de la creation de la tache. Verifiez que cette invite de
    echo commandes est bien lancee "en tant qu'administrateur".
    exit /b 1
)

echo.
echo Tache creee. Demarrage immediat pour verification...
schtasks /Run /TN "%TACHE_NOM%"

echo.
echo Termine. Ouvrez http://127.0.0.1:5100/ dans un navigateur pour verifier.
echo Pour arreter/desactiver plus tard : schtasks /End /TN "%TACHE_NOM%"
echo                                     schtasks /Delete /TN "%TACHE_NOM%" /F
endlocal
