@echo off
REM =============================================================================
REM build-win.bat — Build Locode Setup .exe for Windows
REM Usage: build-win.bat
REM Run from the project root in a standard Command Prompt (not PowerShell)
REM =============================================================================

setlocal enabledelayedexpansion
title Locode Windows Builder

echo.
echo   ============================================
echo     Locode Windows EXE Builder
echo   ============================================
echo.

REM ── 0. Preflight checks ──────────────────────────────────────────────────────
echo [1/8] Preflight checks...

python --version >nul 2>&1 || (echo ERROR: Python not found. Install Python 3.10+ from python.org && exit /b 1)
node --version >nul 2>&1   || (echo ERROR: Node.js not found. Install from nodejs.org && exit /b 1)
npm --version >nul 2>&1    || (echo ERROR: npm not found. Reinstall Node.js && exit /b 1)

if not exist "assets\locode.ico" (
    echo ERROR: Missing assets\locode.ico
    echo        Create a .ico file from your PNG using an online converter
    exit /b 1
)

if not exist "electron\ui\index.html" (
    echo WARNING: electron\ui\index.html not found
    if exist "ui\index.html" (
        xcopy /E /I /Y ui electron\ui >nul
        echo Copied ui\ to electron\ui\
    ) else (
        echo ERROR: No UI found. Build frontend first.
        exit /b 1
    )
)

echo   OK: Preflight passed

REM ── 1. Install Python deps ────────────────────────────────────────────────────
echo [2/8] Installing Python dependencies...
python -m pip install pyinstaller requests websockets watchdog playwright -q
echo   OK: Python deps ready

REM ── 2. Install Node deps ──────────────────────────────────────────────────────
echo [3/8] Installing Node dependencies...
call npm install --silent
echo   OK: Node deps ready

REM ── 3. Download bundled Node.js ───────────────────────────────────────────────
echo [4/8] Preparing bundled Node.js...
if exist "vendor\node\node.exe" (
    echo   OK: Bundled Node.js already present
) else (
    call scripts\download-node-windows.bat
    echo   OK: Node.js downloaded
)

REM ── 4. Bundle Playwright Chromium ─────────────────────────────────────────────
echo [5/8] Preparing bundled Playwright Chromium...
if exist "vendor\ms-playwright" (
    dir /b vendor\ms-playwright | findstr "chromium" >nul 2>&1
    if not errorlevel 1 (
        echo   OK: Playwright Chromium already bundled
        goto :skip_pw
    )
)
echo   Downloading Chromium (this takes a few minutes)...
set PLAYWRIGHT_BROWSERS_PATH=%CD%\vendor\ms-playwright
python -m playwright install chromium
echo   OK: Playwright Chromium bundled
:skip_pw

REM ── 5. Kill stale ports ───────────────────────────────────────────────────────
echo [6/8] Clearing ports 7824 7825 5173...
for %%P in (7824 7825 5173) do (
    for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr :%%P') do (
        taskkill /PID %%A /F >nul 2>&1
    )
)
echo   OK: Ports cleared

REM ── 6. Build PyInstaller backend binary ──────────────────────────────────────
echo [7/8] Building Python backend binary...
if exist "dist" rmdir /S /Q dist
if exist "dist-backend" rmdir /S /Q dist-backend
if exist "build" rmdir /S /Q build

python -m PyInstaller --clean locode-backend-win.spec --noconfirm
if errorlevel 1 (echo ERROR: PyInstaller failed && exit /b 1)

if not exist "dist\locode-backend-v4.exe" (
    echo ERROR: PyInstaller output not found at dist\locode-backend-v4.exe
    exit /b 1
)

mkdir dist-backend
copy dist\locode-backend-v4.exe dist-backend\locode-backend-v4.exe
echo   OK: Backend binary built

REM ── 7. Build Electron NSIS installer ─────────────────────────────────────────
echo [8/8] Building Electron Windows installer...
call npx electron-builder --win nsis
if errorlevel 1 (echo ERROR: electron-builder failed && exit /b 1)

REM Find the installer
set INSTALLER=
for /f "delims=" %%F in ('dir /b release\*.exe 2^>nul') do set INSTALLER=release\%%F

if "%INSTALLER%"=="" (echo ERROR: Installer not found in release\ && exit /b 1)

echo.
echo   ============================================
echo     BUILD COMPLETE!
echo   ============================================
echo.
echo   Installer: %INSTALLER%
echo.
echo   To install: Run %INSTALLER%
echo.