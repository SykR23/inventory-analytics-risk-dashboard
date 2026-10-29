@echo off
REM ---------------------------------------------------------------------------
REM One-click launcher for Windows. Double-click this file.
REM It sets up a local virtual environment, installs dependencies the first
REM time, and opens the dashboard in your browser.
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

REM Find a Python launcher.
where py >nul 2>nul && (set "PY=py") || (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv || (echo Could not create venv. Is Python installed? & pause & exit /b 1)
)

call ".venv\Scripts\activate.bat"

echo Installing/updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Generate demo data if no data tree exists yet.
if not exist "data\Shirts" (
    echo No data found - generating a demo dataset...
    python scripts\make_sample_data.py
)

echo Starting the dashboard...
streamlit run app.py

pause
