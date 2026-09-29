@echo off
title Dich Video Tu Dong - Khoi Dong Giao Dien
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ========================================================
echo   HE THONG DICH VIDEO TU DONG - KHOI DONG GIAO DIEN
echo ========================================================
echo.

:: 1. Kiem tra va khoi tao moi truong ao neu chua co
if not exist ".\.venv\Scripts\python.exe" (
    echo [!] Chua tim thay moi truong ao .venv tren may ban.
    echo [*] Dang tu dong tao moi truong ao Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao moi truong ao .venv. Vui long cai dat Python 3.10 tro len!
        pause
        exit /b 1
    )
)

:: 2. Kiem tra xem da cai Streamlit chua
if not exist ".\.venv\Scripts\streamlit.exe" (
    echo [!] Chua tim thay Streamlit trong .venv.
    echo [*] Dang tu dong cai dat Streamlit va cac goi phu thuoc...
    .\.venv\Scripts\pip install streamlit pandas requests yt-dlp deep-translator srt python-dotenv -i https://mirrors.aliyun.com/pypi/simple/
)

echo Dang khoi dong may chu giao dien Streamlit...
echo Trinh duyet se tu dong mo tai: http://localhost:8501
echo Nhan Ctrl+C de dung chuong trinh.
echo.

if exist ".\.venv\Scripts\streamlit.exe" (
    .\.venv\Scripts\streamlit.exe run app.py
) else (
    .\.venv\Scripts\python.exe -m streamlit run app.py
)

if errorlevel 1 (
    echo.
    echo [CHU Y] Co loi xay ra khi chay Streamlit.
    pause
)
