@echo off
chcp 65001 >nul
title Local Document RAG - Windows

echo ==========================================
echo  Local Document RAG - Windows
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
    echo [1/4] Erstelle virtuelle Umgebung...
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
echo [2/4] Installiere Dependencies...
uv sync
if errorlevel 1 (
    echo Fehler: Konnte Dependencies nicht installieren.
    pause
    exit /b 1
)

REM Alembic Migration
echo [3/4] Datenbank Migration...
alembic upgrade head
if errorlevel 1 (
    echo Warnung: Migration fehlgeschlagen (kann ignoriert werden wenn bereits aktuell).
)

echo.
echo ==========================================
echo [4/4] Starte Server...
echo ==========================================
echo.
echo URL: http://127.0.0.1:5000
echo (Nur auf diesem PC erreichbar)
echo.

python run_windows.py

pause
