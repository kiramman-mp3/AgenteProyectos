@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Agente de Proyectos - Servidor

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual. Ejecuta primero:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo ============================================================
echo  Agente de Seguimiento de Proyectos
echo ============================================================
echo  En la app movil usa como servidor una de estas direcciones
echo  (la de tu red Wi-Fi, con el telefono en la misma red):
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=* delims= " %%b in ("%%a") do echo     http://%%b:8000
)
echo.
echo  Documentacion de la API:  http://localhost:8000/docs
echo  Para detener el servidor:  Ctrl + C
echo ============================================================
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
