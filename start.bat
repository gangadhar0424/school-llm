@echo off
echo ========================================
echo School LLM - Startup Script
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate
echo.

REM Check if .env exists
if not exist ".env" (
    echo WARNING: .env file not found!
    echo Please copy .env.example to .env and add your API keys
    echo.
    pause
    exit /b 1
)

REM Install dependencies if needed
if not exist "venv\Lib\site-packages\fastapi\" (
    echo Installing dependencies...
    cd backend
    pip install -r requirements.txt
    cd ..
    echo.
)

REM Check MongoDB connection
echo Checking MongoDB...
python -c "from pymongo import MongoClient; import os; from dotenv import load_dotenv; load_dotenv(); client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017')); client.server_info(); print('MongoDB connected!')" 2>nul
if errorlevel 1 (
    echo WARNING: Cannot connect to MongoDB
    echo Please ensure MongoDB is running or check your MONGODB_URI in .env
    echo.
)

echo.
echo ========================================
echo Starting School LLM...
echo ========================================
echo.
echo Backend will start on: http://localhost:8000
echo Frontend will start on: http://localhost:3000
echo.
echo Open your browser to: http://localhost:3000/dashboard.html
echo.
echo Press Ctrl+C to stop the servers
echo ========================================
echo.

REM Start backend in new window
start "School LLM Backend" cmd /k "cd backend && venv\Scripts\activate && python main.py"

REM Wait 3 seconds for backend to start
timeout /t 3 /nobreak >nul

REM Start frontend in new window
start "School LLM Frontend" cmd /k "cd frontend && python -m http.server 3000"

REM Wait 2 seconds
timeout /t 2 /nobreak >nul

REM Open browser
start http://localhost:3000/dashboard.html

echo.
echo School LLM is now running!
echo Close this window to keep servers running
echo Or press any key to exit...
pause >nul
