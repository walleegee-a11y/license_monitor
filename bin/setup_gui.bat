@echo off
REM setup_gui.bat - Setup and run License Monitor GUI on Windows
REM
REM This batch script installs dependencies and launches the GUI dashboard
REM

setlocal enabledelayedexpansion

REM Get script directory
for %%I in ("%~dp0.") do set "SCRIPT_DIR=%%~fI"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

echo ================================================
echo License Monitor GUI Setup
echo ================================================

REM Check Python
set PYTHON_BIN=python
%PYTHON_BIN% --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found. Please install Python 3.7+
    pause
    exit /b 1
)

echo Using Python: %PYTHON_BIN%
%PYTHON_BIN% --version

REM Install dependencies
echo.
echo Installing dependencies...
%PYTHON_BIN% -m pip install -q -r "%SCRIPT_DIR%\requirements_gui.txt"
if errorlevel 1 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

REM Set environment variables
set LICENSE_MONITOR_HOME=%PROJECT_ROOT%
set PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%

REM Launch GUI
echo.
echo Launching License Monitor GUI...
echo Database: %PROJECT_ROOT%\db\license_monitor.db
%PYTHON_BIN% "%SCRIPT_DIR%\license_monitor_gui.py"

pause
