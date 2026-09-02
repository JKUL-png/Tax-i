"""Las direcciones de la API para crear, leer y borrar clientes."""

from app import (
    bitacora, checklist, db, documentos, exogena_cliente, formulario,
    vencimientos,
)
from app.api.base import (
    NO_MANDADO, app, campo, campo_lista_de_numeros, campo_texto,
    limpiar_digitos, limpiar_fecha, limpiar_nombre, revisado,
)
from app.servidor import ErrorHttp


# ----------------------------------------------------------
# API de clientes
# ----------------------------------------------------------


@app.get("/api/clientes")
def api_listar_clientes(peticion):
    """Lista los clientes, agregándole a cada uno cuántos documentos tiene."""
    clientes = db.listar_clientes()
    conteos = db.contar_documentos()
    avances = db.contar_checklist()
    for cliente in clientes:
        cliente["documentos"] = conteos.get(cliente["id"], 0)
        avance = avances.get(cliente["id"], {"total": 0, "recibidos": 0})
        cliente["checklist_total"] = avance["total"]
        cliente["checklist_recibidos"] = avance["recibidos"]
    return clientes


@app.get("/api/clientes/{id_cliente}")
def api_obtener_cliente(peticion, id_cliente):
    cliente = db.obtener_cliente(id_cliente)
    if cliente is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return cliente


@app.post("/api/clientes", codigo=201)
def api_crear_cliente(peticion, **partes):
    datos = peticion.diccionario()

    nombre = revisado(limpiar_nombre, campo_texto(datos, "nombre"))
    dos_digitos = revisado(limpiar_digitos, campo_texto(datos, "dos_digitos"))
    fecha = revisado(limpiar_fecha, campo(datos, "fecha_vencimiento"))

    cliente = db.crear_cliente(
        nombre=nombre,
        dos_digitos=dos_digitos,
        fecha_vencimiento=fecha,
        notas=campo(datos, "notas"),
    )
    # El cliente arranca VACÍO, a propósito. Nada se agrega solo.
    #
    # Los renglones salen de una de dos partes, y las dos las decide él:
    # de cargar la exógena en la pestaña Exógena —de ahí salen con el
    # nombre que la propia DIAN les da— o del botón de la lista
    # sugerida, que sigue ahí para el cliente que no tiene exógena.
    bitacora.anotar(cliente["id"], bitacora.CLIENTE_CREADO, cliente["nombre"])
    return cliente


@app.patch("/api/clientes/{id_cliente}")
def api_actualizar_cliente(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    datos = peticion.diccionario()

    # Se distingue "no mandaron el campo" de "lo mandaron vacío para
    # borrarlo". Por eso se mira si la llave está en el JSON, no si su
    # valor es nulo.
    nombre = (revisado(limpiar_nombre, datos["nombre"])
              if "nombre" in datos else None)
    dos_digitos = (revisado(limpiar_digitos, datos["dos_digitos"])
                   if "dos_digitos" in datos else None)
    fecha = (revisado(limpiar_fecha, datos["fecha_vencimiento"])
             if "fecha_vencimiento" in datos else NO_MANDADO)
    notas = datos["notas"] if "notas" in datos else NO_MANDADO

    cliente = db.actualizar_cliente(
        id_cliente,
        nombre=nombre,
        dos_digitos=dos_digitos,
        fecha_vencimiento=fecha,
        notas=notas,
    )
    bitacora.anotar(id_cliente, bitacora.CLIENTE_EDITADO, cliente["nombre"])
    return cliente


@app.delete("/api/clientes/{id_cliente}")
def api_eliminar_cliente(peticion, id_cliente):
    if not db.eliminar_cliente(id_cliente):
        raise ErrorHttp(404, "Ese cliente no existe.")
    # Los documentos de la base se van solos (ON DELETE CASCADE), pero los
    # archivos del disco hay que borrarlos a mano. Son datos confidenciales:
    # no se pueden quedar ahí después de eliminar al cliente.
    documentos.eliminar_carpeta_cliente(id_cliente)
    # Y el archivo de Excel de ese cliente, que también es confidencial.
    formulario.eliminar_carpeta_cliente(id_cliente)
    # Y el reporte de exógena que descargó de la DIAN, por lo mismo.
    exogena_cliente.eliminar_carpeta_cliente(id_cliente)


@app.get("/api/clientes/{id_cliente}/bitacora")
def api_bitacora_cliente(peticion, id_cliente):
    """El historial de actividad de un cliente: qué pasó y cuándo.

    Es lo que se muestra en su perfil. Viene ya con la frase en español
    armada, para que la pantalla no tenga que saber traducir las claves.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")
    return bitacora.historial(id_cliente)


# ----------------------------------------------------------
# Acciones sobre varios clientes de una vez
#
# Después de importar 150 clientes de un Excel, dejarlos listos uno por
# uno son 150 visitas. Estas dos direcciones cierran ese hueco.
# ----------------------------------------------------------


@app.get("/api/vencimientos")
def api_vencimientos(peticion):
    """Dice si hay tabla de vencimientos cargada y de qué años.

    La pantalla usa esto para saber si mostrar o no el botón: sin tabla,
    el botón no aparece y nadie se pregunta por qué no hace nada.
    """
    return {
        "hay_tabla": vencimientos.hay_tabla(),
        "anios": vencimientos.anios_disponibles(),
        "anio": vencimientos.anio_mas_reciente(),
    }


@app.post("/api/clientes/lote/vencimientos")
def api_aplicar_vencimientos(peticion, **partes):
    """Le pone a cada cliente la fecha que le toca según sus dos dígitos.

    La fecha sale de la tabla del calendario oficial que está en
    app/vencimientos.py. El programa NO la calcula: la busca.

    Por defecto solo llena los que están sin fecha. Los que ya tienen una
    no se tocan, porque esa la puso el contador y él manda. Con
    "reemplazar": true se rehacen todos.
    """
    datos = peticion.diccionario()
    anio = campo_texto(datos, "anio", "").strip() or vencimientos.anio_mas_reciente()
    reemplazar = bool(datos.get("reemplazar"))

    if not anio or not vencimientos.hay_tabla(anio):
        raise ErrorHttp(
            409,
            "No hay tabla de vencimientos cargada. Se carga en el archivo"
            " app/vencimientos.py, copiando las fechas del calendario"
            " tributario oficial.",
        )

    problemas = vencimientos.revisar_tabla(anio)
    if problemas:
        # Mejor no aplicar nada que escribirle una fecha mala a 150
        # clientes y que después haya que deshacerlo a mano.
        raise ErrorHttp(
            400,
            "La tabla de vencimientos tiene errores y no se aplicó nada: "
            + problemas[0],
        )

    puestas = 0
    respetadas = 0
    sin_fecha = 0

    for cliente in db.listar_clientes():
        if cliente["fecha_vencimiento"] and not reemplazar:
            respetadas += 1
            continue

        fecha = vencimientos.buscar(cliente["dos_digitos"], anio)
        if not fecha:
            sin_fecha += 1
            continue
        if fecha == cliente["fecha_vencimiento"]:
            respetadas += 1
            continue

        db.actualizar_cliente(cliente["id"], fecha_vencimiento=fecha)
        bitacora.anotar(cliente["id"], bitacora.CLIENTE_EDITADO,
                        "vencimiento del calendario oficial: " + fecha)
        puestas += 1

    return {
        "puestas": puestas,
        "respetadas": respetadas,
        "sin_fecha": sin_fecha,
        "anio": anio,
    }


@app.post("/api/clientes/lote/checklist-base")
def api_lista_base_en_lote(peticion, **partes):
    """Le pone la lista base del checklist a los clientes que no tengan.

    A los que ya tienen renglones NO se les toca nada: su checklist es
    del contador, y agregarle once renglones repetidos sería un estorbo.
    """
    datos = peticion.diccionario()
    ids = campo_lista_de_numeros(datos, "ids") if "ids" in datos else None

    puestos = 0
    saltados = 0

    for cliente in db.listar_clientes():
        if ids is not None and cliente["id"] not in ids:
            continue
        if db.listar_checklist(cliente["id"]):
            saltados += 1
            continue

        renglones = db.crear_renglones(cliente["id"], checklist.LISTA_BASE)
        bitacora.anotar(cliente["id"], bitacora.LISTA_BASE_AGREGADA, "",
                        len(renglones))
        puestos += 1

    return {"puestos": puestos, "saltados": saltados,
            "renglones": len(checklist.LISTA_BASE)}
