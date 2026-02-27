@echo off
REM scripts\download-node-windows.bat
REM Downloads a standalone Node.js binary into vendor\node\
REM Run from the project root: scripts\download-node-windows.bat

setlocal enabledelayedexpansion

set NODE_VERSION=20.18.1
set NODE_ARCH=x64
set NODE_ZIP=node-v%NODE_VERSION%-win-%NODE_ARCH%.zip
set NODE_URL=https://nodejs.org/dist/v%NODE_VERSION%/%NODE_ZIP%
set VENDOR_DIR=%~dp0..\vendor
set NODE_DIR=%VENDOR_DIR%\node

echo Downloading Node.js v%NODE_VERSION% (%NODE_ARCH%) for Windows...
echo URL: %NODE_URL%

if not exist "%VENDOR_DIR%" mkdir "%VENDOR_DIR%"

REM Download using PowerShell (available on all modern Windows)
powershell -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%NODE_URL%' -OutFile '%TEMP%\%NODE_ZIP%' }"

if errorlevel 1 (
    echo ERROR: Download failed
    exit /b 1
)
echo Downloaded successfully

echo Extracting...
if exist "%NODE_DIR%" rmdir /S /Q "%NODE_DIR%"
powershell -Command "Expand-Archive -Path '%TEMP%\%NODE_ZIP%' -DestinationPath '%VENDOR_DIR%' -Force"
rename "%VENDOR_DIR%\node-v%NODE_VERSION%-win-%NODE_ARCH%" "node"

del "%TEMP%\%NODE_ZIP%"

echo.
echo Node.js ready at: vendor\node\
"%NODE_DIR%\node.exe" --version
"%NODE_DIR%\npm.cmd" --version
echo Done!