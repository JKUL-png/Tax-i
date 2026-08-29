#!/bin/sh
# Arma el paquete para llevarse el programa al computador con Windows.
# Doble clic (o ./empacar.sh en la terminal).
#
# Deja un archivo tax-i.zip en el Escritorio, listo para copiar a una
# memoria USB.

cd "$(dirname "$0")" || exit 1

DESTINO="$HOME/Desktop/tax-i.zip"

echo ""
echo "  Armando el paquete para Windows..."
echo ""

# git archive empaca UNICAMENTE lo que está guardado en git. Por eso deja
# afuera solo lo que tiene que dejar afuera, sin que haya que acordarse:
#   .venv/  son programas compilados para Mac; en Windows no sirven
#   datos/  son documentos de clientes de verdad; no viajan
#   .env    lleva la llave de la IA; se pone allá desde la pantalla de Cuenta
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "  No encuentro el repositorio de git en esta carpeta."
  echo "  ¿Está corriendo este archivo desde la carpeta del proyecto?"
  echo ""
  exit 1
fi

# git archive empaca la última versión GUARDADA, no lo que está a medias
# en la carpeta. Si hay cambios sin guardar, se avisa: si no, uno se
# lleva a Windows una versión vieja sin darse cuenta.
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "  ATENCIÓN: hay cambios sin guardar en git."
  echo "  El paquete va a llevar la última versión guardada, no estos"
  echo "  cambios. Si los quiere incluir, haga el commit y vuelva a correr"
  echo "  este archivo."
  echo ""
fi

git archive --format=zip --output="$DESTINO" HEAD || exit 1

CUANTOS=$(unzip -l "$DESTINO" | tail -1 | awk '{print $2}')

echo "  Listo."
echo ""
echo "  El paquete quedó en el Escritorio:  tax-i.zip"
echo "  Trae $CUANTOS archivos, y ninguno es de sus clientes."
echo ""
echo "  Ahora cópielo a una memoria USB y siga con la guía"
echo "  COMO-PROBAR-EN-WINDOWS.md, en la Parte 2."
echo ""
