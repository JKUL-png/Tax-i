#!/bin/sh
# Lanzador para Mac.
# Doble clic (o ./iniciar.sh en la terminal). Prepara todo y prende el servidor.

# Nos paramos en la carpeta del proyecto, sin importar desde dónde se ejecute.
cd "$(dirname "$0")" || exit 1

# La primera vez crea el entorno. Las siguientes lo salta.
if [ ! -d ".venv" ]; then
  echo "Primera vez: preparando el entorno (esto puede tardar un minuto)..."
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install --upgrade pip
fi

# Esto se revisa SIEMPRE, no solo la primera vez: si el proyecto agregó una
# librería nueva, aquí se instala. Cuando ya está todo, tarda un segundo.
.venv/bin/python -m pip install -q -r requirements.txt || exit 1

echo ""
echo "  Asistente de renta corriendo en:  http://localhost:8000"
echo "  Para apagarlo: Control + C"
echo ""

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
