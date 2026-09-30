@echo off
title Creator Studio Pipeline Pro - NVENC Accelerated
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ========================================================
echo   CREATOR STUDIO PIPELINE PRO - KHOI DONG HE THONG
echo   (FastAPI Backend + CapCut Studio Engine + NVENC GPU)
echo ========================================================
echo.

:: 1. Kiem tra moi truong Python .venv
if not exist ".\.venv\Scripts\python.exe" (
    echo [!] Chua tim thay moi truong ao .venv tren may ban.
    echo [*] Dang tao moi truong ao Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao moi truong ao .venv!
        pause
        exit /b 1
    )
)

:: 2. Kiem tra cac goi FastAPI, Uvicorn
if not exist ".\.venv\Lib\site-packages\fastapi" (
    echo [*] Dang cai dat FastAPI va Uvicorn...
    .\.venv\Scripts\pip install fastapi uvicorn pydantic websockets
)

:: 3. Kiem tra ban build React SPA Frontend
if not exist ".\frontend\dist\index.html" (
    echo [*] Dang build giao dien React SPA (Vite + Tailwind)...
    cd frontend && call npm run build && cd ..
)

echo [*] Dang khoi dong may chu Creator Studio tai http://localhost:8000 ...
echo [*] Trinh duyet se tu dong mo trong giay lat...
echo.

:: Mo trinh duyet sau 1.5 giay
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

:: Khoi dong FastAPI server
.\.venv\Scripts\python.exe -m uvicorn src.server.app:app --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo [CHU Y] Co loi xay ra khi chay Studio Server.
    pause
)
