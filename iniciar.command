#!/bin/sh
# Lanzador para Mac que SÍ arranca con doble clic desde el Finder.
#
# ¿Por qué existiendo iniciar.sh?
# Porque el Finder no ejecuta los archivos .sh al hacerles doble clic: los
# abre en un editor de texto. La extensión que el Finder sí entiende como
# "esto se ejecuta" es .command. Son el mismo programa: este solo llama al
# otro, para no tener las instrucciones escritas en dos sitios.
#
# Quien use la terminal puede seguir con ./iniciar.sh, que es igual.
#
# La primera vez, si el programa se bajó de internet, macOS va a decir que
# no puede abrirlo porque viene de un desarrollador no identificado. Es lo
# normal para cualquier programa sin firmar. Se arregla una sola vez:
# clic derecho sobre este archivo -> Abrir -> Abrir.

cd "$(dirname "$0")" || exit 1

# Se llama con sh y no con ./iniciar.sh a propósito: así funciona aunque el
# permiso de ejecución se haya perdido al descomprimir el ZIP.
exec sh ./iniciar.sh
