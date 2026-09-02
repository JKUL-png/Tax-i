"""
La pestaña Exógena: cargar el archivo de la DIAN y trabajar con él.

La exógena es lo que los terceros le reportaron a la DIAN sobre el
cliente. Estas direcciones la cargan, la muestran y dejan que el
contador enlace soportes, decida renglones y lleve valores al 210.

Tres cosas que el programa NO hace aquí, y no son un detalle:

  - No elige cuando la DIAN propone varios renglones. Guarda las
    opciones como ella las escribió y espera.
  - No une ni descarta posibles duplicados. Los marca y dice por qué.
  - No lleva valores solos al 210. Uno por uno, y solo cuando el
    contador lo pide.
"""

from pathlib import Path

from app import bitacora, db, documentos, exogena, exogena_cliente, formulario
from app.api.base import app, campo_texto, cliente_o_404
from app.escribir_210 import EscrituraBloqueada
from app.servidor import ErrorHttp

RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETA_EXOGENA = RAIZ / "datos" / "exogena"

# El reporte de la DIAN es un Excel. Cualquier otra cosa se rechaza
# antes de tocar nada.
EXTENSIONES = (".xlsx", ".xlsm")


def _fila_o_404(id_fila):
    fila = db.obtener_fila_exogena(id_fila)
    if fila is None:
        raise ErrorHttp(404, "Ese registro de la exógena no existe.")
    return fila


@app.get("/api/clientes/{id_cliente}/exogena")
def api_exogena(peticion, id_cliente):
    """Todo lo que la pestaña necesita: avisos, topes, filas y estados."""
    cliente_o_404(id_cliente)
    anio = (peticion.consulta.get("anio") or "").strip()
    return exogena_cliente.tabla(id_cliente, anio or None)


@app.post("/api/clientes/{id_cliente}/exogena", codigo=201)
def api_cargar_exogena(peticion, id_cliente, **partes):
    """Carga el archivo de exógena que el contador descargó de la DIAN.

    El archivo se guarda tal como llegó, para que él pueda volver a
    abrirlo y verlo con sus ojos.
    """
    cliente_o_404(id_cliente)

    archivos = peticion.archivos("archivo")
    if not archivos:
        raise ErrorHttp(400, "No llegó ningún archivo.")
    nombre_original, contenido = archivos[0]

    if Path(nombre_original).suffix.lower() not in EXTENSIONES:
        raise ErrorHttp(
            400,
            "La exógena se descarga del portal de la DIAN como archivo de"
            " Excel (.xlsx). Ese archivo es %s."
            % (Path(nombre_original).suffix or "de otro tipo"),
        )

    carpeta = CARPETA_EXOGENA / str(id_cliente)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = documentos.nombre_libre(
        carpeta, documentos.sanitizar_nombre(nombre_original)
    )
    destino = carpeta / nombre
    destino.write_bytes(contenido)

    try:
        resultado = exogena_cliente.cargar(id_cliente, destino, nombre)
    except exogena.ExogenaInvalida as error:
        # El archivo no sirve: no se deja tirado en el disco.
        destino.unlink(missing_ok=True)
        raise ErrorHttp(400, str(error))

    return resultado


@app.delete("/api/clientes/{id_cliente}/exogena/{anio}")
def api_borrar_exogena(peticion, id_cliente, anio):
    """Quita la exógena de un año. Los renglones del checklist se quedan.

    Se quedan a propósito: pueden tener documentos asignados, y borrar
    los soportes de un cliente en plena temporada es un daño real. Si
    el contador quiere quitarlos, los quita él, uno por uno.
    """
    cliente_o_404(id_cliente)
    if not db.borrar_exogena(id_cliente, anio):
        raise ErrorHttp(404, "No hay exógena cargada de ese año.")


@app.put("/api/exogena/filas/{id_fila}/soporte")
def api_enlazar_soporte(peticion, id_fila):
    """Enlaza el documento que respalda un registro reportado.

    Lo enlaza el contador. El programa a lo sumo le propone uno cuando
    el NIT del tercero aparece en lo que ya se le leyó a un documento,
    y esa propuesta él la confirma o la ignora.
    """
    fila = _fila_o_404(id_fila)
    datos = peticion.diccionario()
    crudo = datos.get("documento_id")

    documento_id = None
    if crudo not in (None, "", 0):
        try:
            documento_id = int(crudo)
        except (TypeError, ValueError):
            raise ErrorHttp(400, "Ese documento no es válido.")
        documento = db.obtener_documento(documento_id)
        if documento is None or documento["cliente_id"] != fila["cliente_id"]:
            raise ErrorHttp(404, "Ese documento no es de este cliente.")

    actualizada = db.enlazar_soporte_exogena(id_fila, documento_id)
    if documento_id:
        bitacora.anotar(fila["cliente_id"], bitacora.EXOGENA_SOPORTE,
                        fila["detalle"][:120])
    return actualizada


@app.put("/api/exogena/filas/{id_fila}/renglon")
def api_elegir_renglon(peticion, id_fila):
    """Guarda el renglón que el contador eligió para un registro.

    Solo se aceptan los códigos que la DIAN propuso en esa fila. El
    programa no elige: si él manda vacío, la fila vuelve a quedar
    esperando su decisión.
    """
    fila = _fila_o_404(id_fila)
    codigo = campo_texto(peticion.diccionario(), "codigo", "").strip().upper()

    if codigo:
        posibles = {r["codigo"] for r in fila["renglones"]}
        if codigo not in posibles:
            raise ErrorHttp(
                400,
                "La DIAN no propone %s para este registro. Propone: %s."
                % (codigo, ", ".join(sorted(posibles)) or "ninguno"),
            )

    actualizada = db.elegir_renglon_exogena(id_fila, codigo)
    if codigo:
        bitacora.anotar(fila["cliente_id"], bitacora.EXOGENA_DECISION,
                        "%s — %s" % (codigo, fila["detalle"][:100]))
    return actualizada


@app.get("/api/exogena/filas/{id_fila}/casillas")
def api_casillas_de_la_fila(peticion, id_fila):
    """En qué casillas del 210 podría ir el valor de este registro.

    Si la fila todavía requiere decisión, no devuelve casillas: primero
    elige él.
    """
    fila = _fila_o_404(id_fila)
    codigo = fila["renglon_elegido"]
    if not codigo and len(fila["renglones"]) == 1:
        codigo = fila["renglones"][0]["codigo"]

    if not codigo:
        return {"codigo": "", "requiere_decision": True, "casillas": []}

    try:
        casillas = formulario.celdas_de_renglon(codigo[1:])
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    return {"codigo": codigo, "requiere_decision": False, "casillas": casillas}


@app.post("/api/exogena/filas/{id_fila}/al-210")
def api_llevar_al_210(peticion, id_fila):
    """Lleva el valor de UN registro a UNA casilla del Formulario 210.

    Uno por uno y con la casilla escogida por el contador. Nunca en
    lote, nunca automático, y nunca un registro que todavía requiera
    decisión: elegir entre los renglones que propone la DIAN es criterio
    profesional.

    La escritura pasa por formulario.guardar_valor, que es la puerta
    donde se revisa que la casilla exista y no tenga fórmula.
    """
    fila = _fila_o_404(id_fila)

    if fila["requiere_decision"] and not fila["renglon_elegido"]:
        raise ErrorHttp(
            409,
            "Este registro tiene más de un renglón posible según la DIAN."
            " Elija primero cuál corresponde.",
        )
    if fila["valor"] is None:
        raise ErrorHttp(400, "Este registro no trae una cifra.")

    celda = campo_texto(peticion.diccionario(), "celda", "").strip().upper()
    if not celda:
        raise ErrorHttp(400, "Falta decir a qué casilla va.")

    de_donde = "Exógena: %s (%s)" % (
        fila["detalle"][:120], fila["nombre_reporta"][:60]
    )
    try:
        guardado = formulario.guardar_valor(
            fila["cliente_id"], celda, fila["valor"], de_donde
        )
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))

    bitacora.anotar(fila["cliente_id"], bitacora.EXOGENA_AL_210,
                    "%s → %s" % (fila["detalle"][:100], celda))
    return guardado
