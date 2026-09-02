"""El Formulario 210 de cada cliente: plantilla, valores y archivo."""

from app import bitacora, db, formulario
from app.api.base import (
    app, campo_numero, campo_texto, cliente_o_404, revisado,
)
from app.escribir_210 import EscrituraBloqueada, VerificacionFallida
from app.servidor import ErrorHttp, Respuesta


# ----------------------------------------------------------
# API del Formulario 210
#
# La plantilla es una sola para todos los clientes. Lo que se guarda por
# cliente son los valores; el archivo de Excel se arma cuando se pide,
# siempre partiendo de la plantilla limpia. Ver app/formulario.py.
# ----------------------------------------------------------


def limpiar_celda(valor):
    """El nombre de una casilla de la plantilla, en mayúsculas: G115."""
    limpia = (valor or "").strip().upper()
    if not limpia:
        raise ValueError("Falta decir en qué casilla va el valor.")
    return limpia


@app.get("/api/plantilla")
def api_plantilla(peticion):
    """Qué plantilla hay puesta y si LibreOffice está disponible."""
    return formulario.resumen_plantilla()


@app.put("/api/plantilla/activa")
def api_elegir_plantilla(peticion, **partes):
    """Cambia la plantilla en uso a otra de las que ya están guardadas."""
    datos = peticion.diccionario()
    try:
        elegida = formulario.elegir_plantilla(campo_texto(datos, "nombre"))
    except formulario.SinPlantilla as error:
        raise ErrorHttp(400, str(error))
    return {"archivo": elegida.name}


@app.post("/api/plantilla", codigo=201)
def api_subir_plantilla(peticion, **partes):
    """Guarda la plantilla que subió el contador y la deja en uso.

    El archivo se guarda tal como llegó. Es de él, con su licencia: el
    programa no le quita ni le cambia nada.
    """
    nombre, contenido = peticion.archivos("archivo")[0]
    try:
        guardada = formulario.guardar_plantilla_subida(nombre, contenido)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(400, str(error))

    resumen = formulario.resumen_plantilla()
    resumen["guardada"] = guardada.name
    return resumen


@app.get("/api/clientes/{id_cliente}/formulario/hoja")
def api_hoja_formulario(peticion, id_cliente):
    """La hoja de captura como se ve para este cliente, para el editor."""
    cliente_o_404(id_cliente)
    try:
        return formulario.hoja_del_cliente(id_cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))


@app.get("/api/plantilla/celdas")
def api_buscar_celdas(peticion, **partes):
    """Busca casillas de la plantilla por palabra, renglón o celda."""
    buscar = peticion.texto_de("buscar", "")
    todas = peticion.si_o_no("todas", False)
    try:
        return formulario.buscar_celdas(buscar, solo_esperadas=not todas)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))


@app.get("/api/clientes/{id_cliente}/formulario")
def api_formulario(peticion, id_cliente):
    """Los valores capturados de un cliente y el estado de su archivo."""
    cliente_o_404(id_cliente)
    try:
        valores = formulario.listar_valores(id_cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    return {"estado": formulario.estado(id_cliente), "valores": valores}


@app.put("/api/clientes/{id_cliente}/formulario/valores")
def api_guardar_valor(peticion, id_cliente):
    """Guarda el valor de una casilla para este cliente."""
    cliente_o_404(id_cliente)

    datos = peticion.diccionario()
    celda = revisado(limpiar_celda, campo_texto(datos, "celda"))
    valor = campo_numero(datos, "valor")
    documento = campo_texto(datos, "documento", "").strip()[:200]

    try:
        return formulario.guardar_valor(id_cliente, celda, valor, documento)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))


@app.delete("/api/clientes/{id_cliente}/formulario/valores/{celda}")
def api_borrar_valor(peticion, id_cliente, celda):
    """Quita un valor capturado. La casilla vuelve a lo que trae la plantilla."""
    cliente_o_404(id_cliente)
    if not db.borrar_valor_210(id_cliente, celda.upper().strip()):
        raise ErrorHttp(404, "Esa casilla no tenía ningún valor.")


@app.get("/api/clientes/{id_cliente}/formulario/bitacora")
def api_bitacora_formulario(peticion, id_cliente):
    """El historial de cambios del formulario de este cliente."""
    cliente_o_404(id_cliente)
    return db.listar_bitacora_210(id_cliente)


@app.post("/api/clientes/{id_cliente}/formulario/generar")
def api_generar_formulario(peticion, id_cliente):
    """Arma el archivo de Excel de este cliente y devuelve cómo salió.

    Con ?totales=si además se le pide a LibreOffice que calcule los totales
    para poder mostrarlos en pantalla. Sin eso —que es lo normal— el
    archivo se entrega igual y Excel calcula los totales al abrirlo. Ver
    `formulario.generar`.
    """
    cliente = cliente_o_404(id_cliente)
    con_totales = peticion.si_o_no("totales", False)
    try:
        salida = formulario.generar(cliente, con_totales=con_totales)
        bitacora.anotar(id_cliente, bitacora.FORMULARIO_GENERADO)
        return salida
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))
    except VerificacionFallida as error:
        # El archivo se descartó. Es un error grave y hay que decirlo tal
        # cual, sin suavizarlo: el contador no debe usar ese archivo.
        raise ErrorHttp(500, str(error))


@app.get("/api/clientes/{id_cliente}/formulario/archivo")
def api_descargar_formulario(peticion, id_cliente):
    """Descarga el archivo de Excel ya generado de este cliente."""
    cliente = cliente_o_404(id_cliente)
    archivo = formulario.archivo_cliente(id_cliente)
    if not archivo.exists():
        raise ErrorHttp(
            404, "Todavía no se ha generado el archivo de este cliente."
        )
    return Respuesta.archivo(
        archivo,
        tipo=("application/vnd.openxmlformats-officedocument"
              ".spreadsheetml.sheet"),
        nombre_visible=formulario.nombre_para_descargar(cliente),
        descargar=True,
    )
