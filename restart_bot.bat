@echo off
echo Stopping existing processes...
taskkill /F /IM python.exe /T 2>nul
taskkill /F /IM node.exe /T 2>nul

echo Starting Zrok Tunnel...
start "Zrok Tunnel" cmd /k "zrok share reserved requiemfinal"

echo Starting Frontend (Next.js)...
cd frontend
start "Frontend" cmd /k "npm run dev"
cd ..

echo Starting Backend (Bot + FastAPI)...
start "Arahnius Bot" cmd /k "venv\Scripts\python main.py > backend_stdout.log 2> backend_stderr.log"

echo Done. Processes started in separate windows with logging to backend_stdout.log and backend_stderr.log.
pause
