@echo off
chcp 65001 >nul
echo Starting Arahnius Bot...

echo Loading configuration from .env...
for /f "usebackq tokens=1,* delims==" %%a in (".env") do set %%a=%%b

echo 1. Launching Bot & Web App...
start "Arahnius Bot" cmd /k "venv\Scripts\python main.py"

echo 2. Launching Zrok Tunnel (%ZROK_SHARE_NAME%)...
start "Zrok Tunnel" cmd /k "zrok share reserved %ZROK_SHARE_NAME%"

echo.
echo Started!
pause
