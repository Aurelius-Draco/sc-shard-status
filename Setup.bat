@echo off
setlocal
title SC Shard Status setup
cd /d "%~dp0"
echo SC Shard Status - one-time setup
echo.

set PY=
py -3.13 -c "import sys" >nul 2>&1 && set PY=py -3.13
if not defined PY py -3.12 -c "import sys" >nul 2>&1 && set PY=py -3.12
if not defined PY python -c "import sys; assert (3,12)<=sys.version_info[:2]<=(3,13)" >nul 2>&1 && set PY=python

if not defined PY (
  echo Python 3.12 or 3.13 was not found.
  echo Install it by running this in a terminal, then run Setup.bat again:
  echo.
  echo     winget install -e --id Python.Python.3.13
  echo.
  pause
  exit /b 1
)

echo Using: %PY%
%PY% -m venv .venv || goto fail
.venv\Scripts\python -m pip install --upgrade pip || goto fail
.venv\Scripts\python -m pip install -r requirements.txt || goto fail
echo.
echo Downloading and warming up the OCR model...
.venv\Scripts\python -c "from rapidocr import RapidOCR; RapidOCR(); print('OCR ready')" || goto fail
echo.
echo Making shortcuts...
choice /c YN /n /m "Also add a Start menu folder and a desktop shortcut? [Y/N] "
set EXTRA=-Extra
if errorlevel 2 set EXTRA=
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launchers\shortcuts.ps1" %EXTRA%
if errorlevel 1 echo Couldn't make the shortcuts. The app still works: use the files in the launchers folder.
echo.
echo Setup complete.
echo   SC Shard Status            start this while you play (opens the dashboard)
echo   SC Shard Status - check    what's gone wrong, printed in a window
echo If you move this folder, run Setup.bat again to fix the shortcuts.
pause
exit /b 0

:fail
echo.
echo Setup failed. Copy the error above into an issue on the project's GitHub page.
pause
exit /b 1
