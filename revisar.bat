@echo off
REM Revisor para Windows.
REM Doble clic. Comprueba que el programa funcione en este computador.
REM
REM Sin tildes a proposito: cmd.exe lee este archivo en una codificacion
REM vieja y una tilde le puede danar la linea entera.

REM Nos paramos en la carpeta del proyecto, sin importar desde donde se ejecute.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto sin_entorno

echo.
echo   Revisando... esto tarda medio minuto.
echo.
.venv\Scripts\python.exe pruebas\revisar_windows.py
goto fin

:sin_entorno
echo.
echo   Todavia no esta preparado el entorno.
echo   Haga doble clic primero en iniciar.bat, espere a que diga
echo   "Tax-i corriendo en...", apaguelo con Control + C, y vuelva aqui.
echo.

:fin
echo.
pause
