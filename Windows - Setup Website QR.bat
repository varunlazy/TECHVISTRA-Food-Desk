@echo off
setlocal
cd /d "%~dp0"
if not exist app\.venv\Scripts\python.exe (
 echo Run Windows - Install and Setup.bat first.
 pause
 exit /b 1
)
app\.venv\Scripts\python.exe app\configure_secure_qr.py
pause
