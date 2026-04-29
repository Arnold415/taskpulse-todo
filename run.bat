@echo off
title TaskPulse - To-Do App
echo.
echo  ========================================
echo    TaskPulse - Smart To-Do App
echo  ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Please install Python 3.x from https://python.org
    echo.
    pause
    exit /b 1
)

echo  Installing / verifying dependencies...
pip install flask flask-login bcrypt google-auth google-auth-oauthlib google-api-python-client --quiet

echo  Starting app...
echo.
start /B cmd /C "timeout /t 2 >nul && start http://localhost:5000"
python app.py
pause
