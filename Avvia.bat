@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Installa Python 3.12 e il launcher py, poi riprova.
        pause
        exit /b 1
    )
)
if not exist ".venv\factory_web_ready" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        pause
        exit /b 1
    )
    type nul > ".venv\factory_web_ready"
)
".venv\Scripts\python.exe" bootstrap_web.py
pause
