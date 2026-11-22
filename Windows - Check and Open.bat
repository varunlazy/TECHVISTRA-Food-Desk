@echo off
setlocal
cd /d "%~dp0"
if not exist app\.venv\Scripts\python.exe (
 echo Run Windows - Install and Setup.bat first while connected to internet.
 pause
 exit /b 1
)
app\.venv\Scripts\python.exe app\launcher.py --open
pause
