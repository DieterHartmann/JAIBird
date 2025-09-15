@echo off
REM JAIBird Multi-Process Startup Script for Windows
REM This launches all JAIBird services in separate processes to avoid async conflicts

echo Starting JAIBird Stock Trading Platform...
echo ==========================================

REM Set the project directory
cd /d "%~dp0"

REM Check if Python environment is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please activate your Python environment first
    pause
    exit /b 1
)

REM Create logs directory if it doesn't exist
if not exist "logs" mkdir logs

REM Start the scheduler process (main scraping and coordination)
echo Starting JAIBird Scheduler...
start "JAIBird-Scheduler" /min cmd /c "python main.py scheduler > logs\scheduler.log 2>&1"

REM Wait a moment for scheduler to initialize
timeout /t 3 /nobreak >nul

REM Start the web interface
echo Starting JAIBird Web Interface...
start "JAIBird-Web" cmd /c "python main.py web > logs\web.log 2>&1"

REM Wait a moment for web to start
timeout /t 2 /nobreak >nul

echo.
echo JAIBird Services Started:
echo - Scheduler: Running in background (minimized)
echo - Web Interface: http://localhost:5000
echo.
echo Log files are in the 'logs' directory:
echo - scheduler.log: Main scraping and notifications
echo - web.log: Web interface activity
echo.
echo To stop JAIBird:
echo - Close this window and the web interface window
echo - Or run: stop_jaibird.bat
echo.

REM Keep this window open to show status
echo JAIBird is now running. Press any key to open web interface...
pause >nul

REM Open web interface in default browser
start http://localhost:5000

echo.
echo JAIBird is running. Close this window to view logs or stop services.
pause
