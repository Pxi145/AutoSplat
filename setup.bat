@echo off
title AutoSplat Studio - Setup Developpeur
color 0B
echo =======================================================
echo     AutoSplat Studio - Setup Environnement
echo =======================================================
echo.

:: --- 1. VERIFICATION DE PYTHON ---
echo [1/3] Verification de Python...
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py -3.12"
) else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_CMD=python"
    ) else (
        color 0C
        echo.
        echo [ERREUR] Python n'a pas ete trouve !
        echo Installez Python 3.12+ en cochant "Add to PATH".
        pause
        exit /b 1
    )
)
echo Python detecte !
echo.

:: --- 2. CREATION DU VENV ---
echo [2/3] Creation de l'environnement virtuel...
if exist "venv\Scripts\python.exe" (
    echo   Venv existant detecte, suppression...
    rmdir /s /q venv
)
%PY_CMD% -m venv venv
if %errorlevel% neq 0 (
    color 0C
    echo [ERREUR] Impossible de creer le venv.
    pause
    exit /b 1
)
echo   Venv cree avec succes !
echo.

:: --- 3. INSTALLATION DES DEPENDANCES ---
echo [3/3] Installation des dependances...
echo (Connexion internet requise)
echo.
venv\Scripts\pip.exe install --upgrade pip >nul 2>&1
venv\Scripts\pip.exe install -r requirements.txt
if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERREUR] Installation des dependances echouee.
    echo Verifiez votre connexion internet.
    pause
    exit /b 1
)

:: --- FIN ---
color 0A
echo.
echo =======================================================
echo     SETUP TERMINE AVEC SUCCES !
echo =======================================================
echo.
echo Pour lancer l'application :
echo   - Double-cliquez sur AutosSplat_Studio.exe.vbs
echo   - Ou executez : venv\Scripts\pythonw.exe main.pyw
echo.
pause
