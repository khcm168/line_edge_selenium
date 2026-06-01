@echo off
setlocal
set TASK_TIME=%~1
if "%TASK_TIME%"=="" set TASK_TIME=09:00
set SCRIPT=%~dp0run_preview.cmd
schtasks /Create /TN "LINE Shipping Notice Preview" /TR "\"%SCRIPT%\"" /SC DAILY /ST %TASK_TIME% /F
echo Installed preview-only scheduled task at %TASK_TIME%.
echo Review Windows Task Scheduler before enabling any live-send workflow.
powershell -NoProfile -Command "Start-Sleep -Seconds 10"

