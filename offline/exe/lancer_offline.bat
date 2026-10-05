@echo off
REM lancer_offline.bat (version EXECUTABLE) — lance MediLogicOffline.exe
REM qui se trouve dans le meme dossier, et le relance s'il s'arrete.
REM Les reglages sont lus dans le fichier .env de ce dossier (voir
REM env.exemple et LISEZMOI.txt). Appele automatiquement par
REM installer_sans_admin.bat / installer_tache_planifiee.bat.

cd /d %~dp0

:boucle
"%~dp0MediLogicOffline.exe"
echo.
echo [%date% %time%] L'appli hors-ligne s'est arretee — relance dans 5 secondes...
timeout /t 5 /nobreak >nul
goto boucle
