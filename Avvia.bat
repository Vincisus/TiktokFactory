@echo off
setlocal
cd /d "%~dp0"
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto ready
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" goto localpython
echo Python 3.12 mancante. Installazione tramite winget...
winget install --exact --id Python.Python.3.12 --scope user
if errorlevel 1 goto failed
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 goto ready
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" goto localpython
goto failed
:ready
py -3.12 avvio_automatico.py
goto finished
:localpython
"%LocalAppData%\Programs\Python\Python312\python.exe" avvio_automatico.py
goto finished
:failed
echo Impossibile installare Python. Installa Python 3.12 da python.org e riprova.
:finished
pause
