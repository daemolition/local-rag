@echo off
chcp 65001 >nul
title Open Knowledge UI - Windows

echo ==========================================
echo  Open Knowledge UI - Windows
echo ==========================================
echo.

REM In Projektverzeichnis wechseln
cd /d "%~dp0"

REM Models Ordner erstellen (falls nicht existiert)
if not exist "models" (
    echo Erstelle models Ordner...
    mkdir models
)

REM Venv pruefen/erstellen
if not exist ".venv" (
    echo [1/5] Erstelle virtuelle Umgebung...
    uv venv
    if errorlevel 1 (
        echo Fehler: Konnte keine virtuelle Umgebung erstellen.
        pause
        exit /b 1
    )
)

REM Venv aktivieren
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo Fehler: Konnte virtuelle Umgebung nicht aktivieren.
    pause
    exit /b 1
)

REM Dependencies installieren
echo [2/5] Installiere Dependencies...
uv sync
if errorlevel 1 (
    echo Fehler: Konnte Dependencies nicht installieren.
    pause
    exit /b 1
)

REM Alembic Migration
echo [3/5] Datenbank Migration...
alembic upgrade head
if errorlevel 1 (
    echo Warnung: Migration fehlgeschlagen (kann ignoriert werden wenn bereits aktuell).
)

REM React-Frontend bauen (falls Node/npm vorhanden und noch kein Build da)
echo [4/5] Frontend pruefen...
if not exist "app\static\index.html" (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo Warnung: npm nicht gefunden - Frontend kann nicht gebaut werden.
        echo Installiere Node.js und fuehre aus: cd frontend ^&^& npm install ^&^& npm run build
    ) else (
        pushd frontend
        call npm install
        call npm run build
        popd
    )
)

echo.
echo ==========================================
echo [5/5] Starte Server...
echo ==========================================
echo.
echo URL: http://127.0.0.1:5000
echo (Nur auf diesem PC erreichbar)
echo.

python run_windows.py

pause
