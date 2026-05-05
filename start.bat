@echo off
REM HibsBetting startup script for Windows

setlocal enabledelayedexpansion

echo 🟤💛 HibsBetting Launcher
echo.

REM Check if .env exists
if not exist ".env" (
    echo No .env file found. Running setup...
    python src\hibs_predictor\main.py setup
    echo.
)

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import flask, pandas, sklearn, requests" 2>nul
if errorlevel 1 (
    echo Installing requirements...
    python -m pip install -q -r requirements.txt
)

echo.
echo Starting web dashboard...
echo Visit: http://127.0.0.1:5000
echo.

python src\hibs_predictor\main.py web
