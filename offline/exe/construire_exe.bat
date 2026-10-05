@echo off
REM offline/exe/construire_exe.bat — construit MediLogicOffline.exe (PC de
REM developpement UNIQUEMENT ; le PC client ne fait que recevoir le dossier
REM produit). A lancer depuis la racine du depot :
REM     offline\exe\construire_exe.bat
REM Prerequis : pip install pyinstaller (une fois). Produit le dossier
REM     dist\MediLogicOffline\   (exe + .bat + env.exemple + LISEZMOI.txt)
REM a copier tel quel sur le PC client (cle USB).

setlocal
cd /d %~dp0..\..
python -m PyInstaller --noconfirm --clean --distpath dist\_build --workpath build\pyinstaller offline\exe\medilogic_offline.spec
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ECHEC de la construction. Verifiez que PyInstaller est installe :  python -m pip install pyinstaller
    exit /b 1
)
set SORTIE=dist\MediLogicOffline
if exist "%SORTIE%" rmdir /s /q "%SORTIE%"
mkdir "%SORTIE%"
copy /y dist\_build\MediLogicOffline.exe "%SORTIE%\" >nul
copy /y offline\exe\lancer_offline.bat "%SORTIE%\" >nul
copy /y offline\exe\env.exemple "%SORTIE%\" >nul
copy /y offline\exe\LISEZMOI.txt "%SORTIE%\" >nul
copy /y offline\installer_sans_admin.bat "%SORTIE%\" >nul
copy /y offline\installer_tache_planifiee.bat "%SORTIE%\" >nul
echo.
echo Termine : %SORTIE%\
dir /b "%SORTIE%"
endlocal
