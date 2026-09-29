@echo off
REM offline/installer_sans_admin.bat
REM Alternative a installer_tache_planifiee.bat pour un PC ou l'utilisateur
REM n'a PAS les droits administrateur. Ne necessite AUCUNE elevation :
REM depose un petit fichier dans le dossier "Demarrage" personnel de
REM l'utilisateur (%APPDATA%\...\Startup), que Windows execute
REM automatiquement a chaque connexion — sans passer par le Planificateur
REM de taches. A executer UNE SEULE FOIS, depuis le dossier racine du
REM projet (ex: C:\medilogic_ghp), en double-cliquant ou depuis une
REM invite de commandes normale (pas besoin de "Executer en tant
REM qu'administrateur").

setlocal
set SCRIPT=%~dp0lancer_offline.bat
set DEMARRAGE=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set STUB=%DEMARRAGE%\MediLogicOffline.bat

if not exist "%SCRIPT%" (
    echo ERREUR : %SCRIPT% introuvable. Lancez ce script depuis le dossier
    echo racine du projet ^(ex: C:\medilogic_ghp^).
    exit /b 1
)

echo Creation du lanceur automatique dans le dossier Demarrage...
> "%STUB%" echo @echo off
>> "%STUB%" echo start "" /min "%SCRIPT%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ECHEC de l'ecriture dans %DEMARRAGE%
    exit /b 1
)

echo.
echo Fichier cree : %STUB%
echo Il sera execute automatiquement a la PROCHAINE connexion Windows de
echo cet utilisateur ^(ouverture de session^).
echo.
echo Pour le demarrer MAINTENANT sans attendre ^(verification^) :
echo   call "%SCRIPT%"
echo.
echo Pour desactiver plus tard : supprimez simplement le fichier
echo   %STUB%
endlocal
