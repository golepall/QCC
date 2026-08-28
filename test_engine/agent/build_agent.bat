@echo off
echo ========================================
echo   QCC Offline Test Workbench - PyInstaller Build
echo ========================================
echo.

cd /d "%~dp0\.."
echo Working dir: %CD%
echo.

echo [1/2] Building with PyInstaller...
python -m PyInstaller ^
    --onedir ^
    --name QCC_Test_Agent ^
    --add-data "core;core" ^
    --add-data "script_registry.json;." ^
    --add-data "scripts;scripts" ^
    --hidden-import psutil ^
    --hidden-import tkinter ^
    --noconfirm ^
    --clean ^
    agent\agent_runner.py

if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo [2/2] Build complete!
echo Output: dist\QCC_Test_Agent\QCC_Test_Agent.exe
echo This build includes bundled collectors and script registry for exe delivery.
echo.
pause
