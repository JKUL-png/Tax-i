@echo off
REM Lanzador para Windows.
REM Doble clic. Prepara todo y prende el servidor.

REM Nos paramos en la carpeta del proyecto, sin importar desde donde se ejecute.
cd /d "%~dp0"

REM La primera vez crea el entorno. Las siguientes lo salta.
if not exist ".venv" goto instalar
goto revisar

:instalar
echo Primera vez: preparando el entorno (esto puede tardar un minuto)...
py -m venv .venv
if errorlevel 1 goto sin_python
.venv\Scripts\python.exe -m pip install --upgrade pip

:revisar
REM Esto se revisa SIEMPRE, no solo la primera vez: si el proyecto agrego una
REM libreria nueva, aqui se instala. Cuando ya esta todo, tarda un segundo.
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 goto error

:arrancar
echo.
echo   Tax-i corriendo en:                http://localhost:8000
echo   Para apagarlo: Control + C
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto fin

:sin_python
echo.
echo   No se encontro Python. Instalalo desde https://www.python.org/downloads/
echo   IMPORTANTE: marcar la casilla "Add Python to PATH" durante la instalacion.
echo.
goto fin

:error
echo.
echo   Hubo un problema instalando las dependencias.
echo.

:fin
pause
