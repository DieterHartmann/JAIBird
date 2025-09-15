@echo off
REM JAIBird Service Stopper for Windows

echo Stopping JAIBird Services...
echo ============================

REM Kill JAIBird processes by window title
taskkill /fi "windowtitle eq JAIBird-Scheduler" /f >nul 2>&1
taskkill /fi "windowtitle eq JAIBird-Web" /f >nul 2>&1

REM Also kill any python processes running JAIBird
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo csv ^| findstr "main.py"') do (
    taskkill /pid %%i /f >nul 2>&1
)

echo JAIBird services stopped.
echo.
echo Log files are preserved in the 'logs' directory.
echo.
pause
