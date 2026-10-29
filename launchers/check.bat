@echo off
title SC Shard Status - what's gone wrong
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Run Setup.bat in the SC Shard Status folder first.
  pause
  exit /b 1
)
.venv\Scripts\python status.py --check %*
pause
