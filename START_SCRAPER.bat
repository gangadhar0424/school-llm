@echo off
REM Web Scraper Scheduler Startup Script
REM This runs the scraper independently in the background

echo ========================================
echo  SCHOOL LLM - Web Scraper Scheduler
echo ========================================
echo.

cd /d "%~dp0backend"

echo [1/2] Activating virtual environment...
call ..\venv\Scripts\activate.bat

echo [2/2] Starting scraper scheduler...
echo.
echo The scraper will run every 6 hours automatically.
echo Data will be saved to MongoDB continuously.
echo.
echo Press CTRL+C to stop the scheduler
echo ========================================
echo.

python scraper_scheduler.py

pause
