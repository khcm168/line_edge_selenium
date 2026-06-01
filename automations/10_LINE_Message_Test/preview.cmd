@echo off
setlocal
cd /d "%~dp0\..\.."
set PYTHON_EXE=%CD%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" -m app.line_batch --test-targets %*
powershell -NoProfile -Command "Start-Sleep -Seconds 10"

