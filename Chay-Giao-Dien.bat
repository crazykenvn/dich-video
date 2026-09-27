@echo off
title Dich Video Tieng Trung Sang Tieng Viet
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ========================================================
echo   HE THONG DICH VIDEO TIENG TRUNG - KHOI DONG GIAO DIEN
echo ========================================================
echo.
echo Dang khoi dong may chu giao dien Streamlit...
echo Trinh duyet se tu dong mo tai: http://localhost:8501
echo Nhan Ctrl+C de dung chuong trinh.
echo.

.\.venv\Scripts\streamlit run app.py
pause
