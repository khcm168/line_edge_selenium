@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=.venv\Scripts\python.exe
"%PYTHON_EXE%" -m app.reminder_builder %*
