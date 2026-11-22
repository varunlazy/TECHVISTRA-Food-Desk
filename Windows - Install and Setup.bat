@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if errorlevel 1 (
 echo Installing Python 3.12. Internet is required. Approve the Windows installer when prompted.
 winget install --id Python.Python.3.12 --exact --source winget --accept-package-agreements --accept-source-agreements
 if errorlevel 1 goto failed
)
where py >nul 2>nul
if not errorlevel 1 (
 py -3 app\launcher.py --setup
) else (
 if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  "%LocalAppData%\Programs\Python\Python312\python.exe" app\launcher.py --setup
 ) else (
  echo Python installed. Close this window and run this file again to refresh PATH.
  goto failed
 )
)
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Setup could not finish. Review the error above. If winget is unavailable, install Python 3.12 from https://www.python.org/downloads/ and run this file again.
pause
exit /b 1
