"""Subir, listar, abrir, asignar y borrar los documentos de un cliente."""

import mimetypes
from pathlib import Path

from app import (
    bitacora, checklist, clasificacion, db, documentos, extraccion,
    importar, lectura,
)
from app.api.base import app, campo_lista_de_numeros, cliente_o_404
from app.servidor import ErrorHttp, Respuesta


# ----------------------------------------------------------
# API de documentos
# ----------------------------------------------------------


def con_tipo(documento):
    """Le agrega al documento lo que la pantalla necesita para mostrarlo."""
    documento = dict(documento)
    documento["tipo"] = documentos.tipo_legible(documento["extension"])
    documento["vista"] = documentos.como_se_previsualiza(documento["extension"])
    return documento


def guardar_y_registrar(id_cliente, nombre_original, contenido,
                        huella, venia_en_zip=None):
    """Escribe el archivo en el disco y lo anota en la base de datos."""
    nombre_guardado, tamano = documentos.guardar_contenido(
        id_cliente, nombre_original, contenido
    )
    registro = db.crear_documento(
        cliente_id=id_cliente,
        nombre_original=nombre_original,
        nombre_guardado=nombre_guardado,
        extension=Path(nombre_guardado).suffix.lower(),
        tamano=tamano,
        huella=huella,
        venia_en_zip=venia_en_zip,
    )
    return con_tipo(registro)


@app.get("/api/clientes/{id_cliente}/documentos")
def api_listar_documentos(peticion, id_cliente):
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    renglones = db.listar_checklist(id_cliente)
    guardadas = db.sugerencias_del_cliente(id_cliente)
    salida = []

    for documento in db.listar_documentos(id_cliente):
        documento = con_tipo(documento)

        # A los que todavía nadie asignó se les PROPONE un renglón. La
        # propuesta la hizo el código, no la IA, y sale con el origen a
        # la vista: por la exógena, por el XML, por el texto o por el
        # nombre del archivo. Aceptar es un clic; cambiarla también.
        #
        # 'sugerencia' se queda como el id a secas porque es lo que la
        # pantalla ya sabía leer, y 'sugerencias' trae el detalle.
        documento["sugerencia"] = None
        documento["sugerencias"] = []

        if documento["renglon_id"] is None:
            propuestas = guardadas.get(documento["id"], [])
            if not propuestas:
                # Todavía no le ha tocado el turno en la fila de
                # clasificación —o viene de una versión anterior del
                # programa—, así que por lo menos se mira el nombre.
                sugerido, palabras = lectura.sugerir_renglon(
                    documento["nombre_original"], renglones
                )
                if sugerido is not None:
                    propuestas = [{
                        "renglon_id": sugerido,
                        "origen": clasificacion.POR_NOMBRE,
                        "certeza": clasificacion.MEDIA,
                        "porque": "El nombre del archivo y el del renglón"
                                  " comparten: %s." % ", ".join(palabras),
                        "principal": True,
                    }]

            for propuesta in propuestas:
                documento["sugerencias"].append({
                    "renglon_id": propuesta["renglon_id"],
                    "origen": propuesta["origen"],
                    "origen_texto": clasificacion.ORIGENES.get(
                        propuesta["origen"], propuesta["origen"]),
                    "certeza": propuesta["certeza"],
                    "porque": propuesta["porque"],
                })
            if documento["sugerencias"]:
                documento["sugerencia"] = documento["sugerencias"][0][
                    "renglon_id"]

        salida.append(documento)

    return salida


@app.post("/api/clientes/{id_cliente}/documentos")
def api_subir_documentos(peticion, id_cliente):
    """Recibe uno o varios archivos y los guarda en la carpeta del cliente.

    Los ZIP se abren y se guarda lo que traen adentro, no el ZIP.
    Lo que no se pueda guardar se devuelve en la lista `ignorados`, con el
    motivo, para poder mostrárselo al contador en vez de fallar en silencio.
    """
    if db.obtener_cliente(id_cliente) is None:
        raise ErrorHttp(404, "Ese cliente no existe.")

    guardados = []
    ignorados = []

    for nombre_completo, contenido in peticion.archivos("archivos"):
        nombre_completo = nombre_completo or "documento"

        # Basura del sistema: se salta sin avisar, no es un documento.
        if documentos.es_basura(nombre_completo):
            continue

        # El navegador puede mandar la ruta de la carpeta cuando se arrastra
        # una carpeta completa. Aquí solo interesa el nombre del archivo.
        nombre = nombre_completo.replace("\\", "/").split("/")[-1]
        extension = Path(nombre).suffix.lower()

        # --- Caso ZIP: se abre y se guarda lo de adentro ---
        if extension == ".zip":
            if documentos.dentro_del_limite(contenido,
                                            documentos.LIMITE_ZIP) is None:
                ignorados.append(nombre + " — el ZIP pesa más de 100 MB.")
                continue

            encontrados, motivos = documentos.abrir_zip(contenido)
            ignorados.extend(motivos)

            if not encontrados and not motivos:
                ignorados.append(nombre + " — el ZIP no traía documentos útiles.")

            for nombre_interno, datos in encontrados:
                huella = documentos.huella_del_contenido(datos)
                repetido = db.buscar_documento_por_huella(id_cliente, huella)
                if repetido:
                    ignorados.append(
                        nombre_interno + " — ya estaba subido como \""
                        + repetido["nombre_original"] + "\"."
                    )
                    continue
                guardados.append(
                    guardar_y_registrar(
                        id_cliente, nombre_interno, datos, huella, nombre
                    )
                )
            continue

        # --- Caso archivo suelto ---
        if extension not in documentos.EXTENSIONES_PERMITIDAS:
            ignorados.append(nombre + " — tipo de archivo no admitido.")
            continue

        if documentos.dentro_del_limite(contenido,
                                        documentos.LIMITE_ARCHIVO) is None:
            ignorados.append(nombre + " — pesa más de 25 MB.")
            continue
        if not contenido:
            ignorados.append(nombre + " — el archivo está vacío.")
            continue

        # ¿Este cliente ya mandó exactamente este mismo archivo?
        # Se compara el contenido, no el nombre.
        huella = documentos.huella_del_contenido(contenido)
        repetido = db.buscar_documento_por_huella(id_cliente, huella)
        if repetido:
            ignorados.append(
                nombre + " — ya estaba subido como \""
                + repetido["nombre_original"] + "\"."
            )
            continue

        guardados.append(
            guardar_y_registrar(id_cliente, nombre, contenido, huella)
        )

    if guardados:
        # Una sola anotación por tanda, con cuántos entraron. Si fue uno
        # solo, se guarda además su nombre; si fueron varios, el detalle
        # sería una lista larguísima que no ayuda a nadie.
        detalle = guardados[0]["nombre_original"] if len(guardados) == 1 else ""
        bitacora.anotar(id_cliente, bitacora.DOCUMENTOS_SUBIDOS,
                        detalle, len(guardados))

    # Los XML se leen aquí mismo, de una. Es gratis, es exacto, tarda
    # milisegundos y no sale del computador: no hay ninguna razón para
    # hacérselo pedir. El texto de los PDF se lee después, todo junto,
    # en la pasada del formulario — eso sí cuesta y lo pide él.
    leidos = 0
    if guardados:
        leidos = sum(
            1 for informe in extraccion.leer_xml_pendientes(id_cliente)
            if informe["estado"] == "listo"
        )
        # La clasificación también arranca sola, por lo mismo: es gratis
        # y pasa entera en este computador. Lo que se le pide al contador
        # es gastar plata, no trabajar.
        clasificacion.arrancar(id_cliente)

    return {
        "guardados": guardados,
        "ignorados": ignorados,
        "xml_leidos": leidos,
        "estado": extraccion.resumen(id_cliente),
    }


# ----------------------------------------------------------
# Lo que se le sacó a los documentos
#
# Cada documento se lee UNA vez y lo que se le sacó queda en la base.
# Después RentAI contesta con esas filas y no vuelve a leer —ni a pagar—
# los mismos documentos.
#
# Hay dos formas de llegar a esa tabla, y ninguna cuesta aparte: los XML
# los lee el programa al confirmar la carga (app/extraccion.py), y de
# los PDF los saca la pasada del formulario, en la misma llamada con la
# que propone los renglones (app/pasada.py).
# ----------------------------------------------------------


@app.get("/api/clientes/{id_cliente}/datos")
def api_datos_extraidos(peticion, id_cliente):
    """Los datos que ya se le sacaron a los documentos de este cliente.

    Cada dato dice de qué documento salió y quién lo leyó: 'codigo' si lo
    leyó el programa de un XML (es exacto), o 'pasada' si salió de la
    propuesta del formulario (es lectura automática, viene con su cita
    ya verificada y hay que revisarla contra el original).

    Esto funciona con IA_PROVEEDOR=ninguno: lo ya leído está en este
    computador y no hay a quién preguntarle.
    """
    cliente_o_404(id_cliente)
    return {
        "estado": extraccion.resumen(id_cliente),
        "datos": db.listar_datos_extraidos(id_cliente),
    }


@app.post("/api/clientes/{id_cliente}/datos/procesar")
def api_leer_xml(peticion, id_cliente):
    """Lee los XML de este cliente que estén sin leer.

    Contesta cuando terminó, no antes: parsear un XML tarda
    milisegundos, así que no hace falta una fila ni un hilo aparte.
    Antes esto ponía a leer los PDF con IA, que se demoraba minutos —
    de ahí venía toda esa maquinaria. Ahora los PDF los lee la pasada.
    """
    cliente_o_404(id_cliente)
    informes = extraccion.leer_xml_pendientes(id_cliente)
    leidos = sum(1 for informe in informes if informe["estado"] == "listo")
    if leidos:
        bitacora.anotar(id_cliente, bitacora.DOCUMENTOS_LEIDOS)
    return {"leidos": leidos, "estado": extraccion.resumen(id_cliente)}


@app.get("/api/documentos/{id_documento}/archivo")
def api_abrir_documento(peticion, id_documento):
    """Entrega el archivo original para verlo en el navegador."""
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.is_file():
        raise ErrorHttp(404, "El archivo ya no está en el disco.")

    tipo, _ = mimetypes.guess_type(documento["nombre_guardado"])

    # Se manda "inline" para que el navegador lo muestre en vez de
    # descargarlo, y el nombre codificado para que las tildes y las eñes
    # no se dañen. De eso se encarga Respuesta.archivo.
    return Respuesta.archivo(
        ruta,
        tipo=tipo or "application/octet-stream",
        nombre_visible=documento["nombre_original"],
        descargar=False,
    )


@app.delete("/api/documentos/{id_documento}")
def api_eliminar_documento(peticion, id_documento):
    """Borra un documento suelto. El archivo va a la papelera, no al vacío."""
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    # Primero el archivo, después el registro. Si el archivo no se puede
    # mover, no se borra la fila: es preferible ver el documento en la
    # lista a que la lista mienta sobre lo que hay en el disco.
    documentos.mandar_a_papelera(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    db.eliminar_documento(id_documento)

    bitacora.anotar(documento["cliente_id"], bitacora.DOCUMENTOS_BORRADOS,
                    documento["nombre_original"], 1)


@app.post("/api/clientes/{id_cliente}/documentos/eliminar")
def api_eliminar_documentos(peticion, id_cliente):
    """Borra varios documentos de un cliente de un solo golpe.

    La dirección lleva el cliente A PROPÓSITO. El servidor solo borra los
    documentos que de verdad son de ese cliente: si en la lista viene el
    id de un documento de otro, se queda quieto. La pantalla se puede
    engañar, así que la comprobación se hace aquí.

    Es POST y no DELETE porque hay que mandarle una lista de ids en el
    cuerpo, y no todos los navegadores mandan cuerpo en un DELETE.

    Devuelve cuántos se borraron y el nombre de cada uno, para poder
    decirle al contador exactamente qué desapareció.
    """
    cliente = cliente_o_404(id_cliente)

    datos = peticion.diccionario()
    ids = campo_lista_de_numeros(datos, "ids")
    if not ids:
        raise ErrorHttp(400, "No se marcó ningún documento para borrar.")

    encontrados = db.documentos_de(id_cliente, ids)
    if not encontrados:
        raise ErrorHttp(
            404, "Ninguno de esos documentos es de este cliente."
        )

    nombres = []
    for documento in encontrados:
        documentos.mandar_a_papelera(id_cliente, documento["nombre_guardado"])
        nombres.append(documento["nombre_original"])

    borrados = db.eliminar_documentos(id_cliente, [d["id"] for d in encontrados])

    detalle = nombres[0] if len(nombres) == 1 else ""
    bitacora.anotar(id_cliente, bitacora.DOCUMENTOS_BORRADOS, detalle, borrados)

    return {
        "borrados": borrados,
        "nombres": nombres,
        "cliente": cliente["nombre"],
        # Cuántos venían en la lista pero no eran de este cliente. Si sale
        # distinto de cero, algo está mal en la pantalla y hay que verlo.
        "ignorados": len(ids) - len(encontrados),
    }


# ----------------------------------------------------------
# Asignar un documento a un renglón del checklist
#
# Esto es lo que conecta las dos mitades del programa: el archivo que
# llegó y la casilla que lo estaba esperando. Por ahora lo hace el
# contador a mano; más adelante se le puede sugerir automáticamente.
# ----------------------------------------------------------


@app.patch("/api/documentos/{id_documento}")
def api_asignar_documento(peticion, id_documento):
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    datos = peticion.diccionario()
    renglon_id = datos.get("renglon_id")

    if renglon_id is not None:
        if not isinstance(renglon_id, int) or isinstance(renglon_id, bool):
            raise ErrorHttp(400, "El renglón tiene que ser un número.")

        renglon = db.obtener_renglon(renglon_id)
        if renglon is None:
            raise ErrorHttp(404, "Ese renglón no existe.")
        if renglon["cliente_id"] != documento["cliente_id"]:
            raise ErrorHttp(400, "Ese renglón es de otro cliente.")
        # Asignar un documento a un renglón es decir "esto ya llegó",
        # así que el renglón se marca recibido solo.
        db.actualizar_renglon(renglon_id, estado=checklist.RECIBIDO)

    asignado = con_tipo(db.asignar_documento(id_documento, renglon_id))
    if renglon_id is not None:
        bitacora.anotar(documento["cliente_id"], bitacora.DOCUMENTO_ASIGNADO,
                        documento["nombre_original"])
        # Lo más valioso que pasa en el programa: el contador acaba de
        # enseñar dónde va este tipo de documento. Se guarda para no
        # volver a proponerle lo mismo mal, y sirve en todos sus
        # clientes. Ver app/clasificacion.py.
        try:
            clasificacion.aprender_de_la_correccion(documento, renglon_id)
        except Exception:
            # Aprender es una mejora, no un requisito: si falla, la
            # asignación que él pidió ya quedó hecha y eso es lo que
            # importa.
            pass
    asignado["renglones"] = db.renglones_del_documento(id_documento)
    return asignado


@app.post("/api/documentos/{id_documento}/renglones", codigo=201)
def api_agregar_renglon(peticion, id_documento):
    """Le suma un renglón a un documento SIN quitarle los que ya tenía.

    Un certificado de ingresos y retenciones soporta el ingreso en un
    renglón y la retención en otro. Obligar a elegir uno solo sería
    obligar a subir el mismo papel dos veces.
    """
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    renglon_id = peticion.diccionario().get("renglon_id")
    if not isinstance(renglon_id, int) or isinstance(renglon_id, bool):
        raise ErrorHttp(400, "El renglón tiene que ser un número.")
    renglon = db.obtener_renglon(renglon_id)
    if renglon is None:
        raise ErrorHttp(404, "Ese renglón no existe.")
    if renglon["cliente_id"] != documento["cliente_id"]:
        raise ErrorHttp(400, "Ese renglón es de otro cliente.")

    db.actualizar_renglon(renglon_id, estado=checklist.RECIBIDO)
    renglones = db.agregar_renglon_a_documento(id_documento, renglon_id)
    bitacora.anotar(documento["cliente_id"], bitacora.DOCUMENTO_ASIGNADO,
                    documento["nombre_original"])
    return {"renglones": renglones}


@app.delete("/api/documentos/{id_documento}/renglones/{id_renglon}")
def api_quitar_renglon(peticion, id_documento, id_renglon):
    """Le quita UN renglón a un documento. Los otros se quedan."""
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")
    db.quitar_renglon_de_documento(id_documento, int(id_renglon))


@app.post("/api/clientes/{id_cliente}/documentos/aceptar-sugerencias")
def api_aceptar_sugerencias(peticion, id_cliente):
    """Acepta de un golpe las sugerencias de certeza alta.

    El contador ve la lista ANTES de confirmar —la pantalla se la
    muestra— y manda aquí los documentos que aprobó. No se acepta nada
    que él no haya mirado: por eso van los ids y no un «acepte todas».
    """
    cliente_o_404(id_cliente)
    ids = campo_lista_de_numeros(peticion.diccionario(), "ids")
    if not ids:
        raise ErrorHttp(400, "No llegó ningún documento que aceptar.")

    guardadas = db.sugerencias_del_cliente(id_cliente)
    aceptados = 0

    for id_documento in ids:
        documento = db.obtener_documento(id_documento)
        if documento is None or documento["cliente_id"] != id_cliente:
            continue
        if documento["renglon_id"] is not None:
            continue
        propuestas = [s for s in guardadas.get(id_documento, [])
                      if s["certeza"] == clasificacion.ALTA]
        if not propuestas:
            continue
        renglon_id = propuestas[0]["renglon_id"]
        if db.obtener_renglon(renglon_id) is None:
            continue
        db.actualizar_renglon(renglon_id, estado=checklist.RECIBIDO)
        db.asignar_documento(id_documento, renglon_id)
        aceptados += 1

    if aceptados:
        bitacora.anotar(id_cliente, bitacora.DOCUMENTO_ASIGNADO, "", aceptados)
    return {"aceptados": aceptados}


@app.post("/api/clientes/{id_cliente}/documentos/clasificar")
def api_clasificar(peticion, id_cliente):
    """Vuelve a mirar los documentos sin asignar.

    Es gratis y pasa entero en este computador: exógena, XML, texto y
    nombre del archivo. No cuesta un peso y no sale nada.

    Antes tenía un interruptor para preguntarle además al modelo por los
    que no supo ubicar. Ese trabajo lo hace ahora la pasada del
    formulario, mirando todo el cliente junto en vez de un documento
    suelto a la vez, que es como se acierta.
    """
    cliente_o_404(id_cliente)
    db.marcar_para_clasificar(id_cliente)
    return {"arrancó": clasificacion.arrancar(id_cliente)}


# ----------------------------------------------------------
# Vista previa de un documento
#
# La idea es que el contador pueda mirar qué es un archivo sin tener
# que descargarlo y abrirlo en otro programa.
# ----------------------------------------------------------

# Cuánto se muestra de una hoja de cálculo o de un XML en la vista previa.
# Es una mirada rápida, no el archivo completo.
FILAS_EN_VISTA = 60
COLUMNAS_EN_VISTA = 15
LETRAS_EN_VISTA = 20000


@app.get("/api/documentos/{id_documento}/vista")
def api_vista_documento(peticion, id_documento):
    """Prepara lo que hace falta para mostrar el documento en pantalla.

    Los PDF y las imágenes los sabe mostrar el navegador solo, así que
    para esos basta con devolver la dirección del archivo. El XML y las
    hojas de cálculo hay que leerlos aquí.
    """
    documento = db.obtener_documento(id_documento)
    if documento is None:
        raise ErrorHttp(404, "Ese documento no existe.")

    vista = documentos.como_se_previsualiza(documento["extension"])
    direccion = "/api/documentos/" + str(id_documento) + "/archivo"

    if vista in ("pdf", "imagen"):
        return {"vista": vista, "url": direccion}

    if vista == "sin_vista":
        return {
            "vista": "sin_vista",
            "url": direccion,
            "motivo": (
                "Las fotos de iPhone (.heic) no las muestra el navegador."
                if documento["extension"] in (".heic", ".heif")
                else "Este tipo de archivo no se puede ver aquí."
            ),
        }

    ruta = documentos.ruta_del_documento(
        documento["cliente_id"], documento["nombre_guardado"]
    )
    if ruta is None or not ruta.is_file():
        raise ErrorHttp(404, "El archivo ya no está en el disco.")

    contenido = ruta.read_bytes()

    # --- XML: se muestra el texto tal cual ---
    if vista == "texto":
        texto = None
        for codificacion in ("utf-8", "cp1252", "latin-1"):
            try:
                texto = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue
        if texto is None:
            return {"vista": "sin_vista", "url": direccion,
                    "motivo": "No se pudo leer el texto del archivo."}

        recortado = len(texto) > LETRAS_EN_VISTA
        return {
            "vista": "texto",
            "url": direccion,
            "texto": texto[:LETRAS_EN_VISTA],
            "recortado": recortado,
            # Si es una factura electrónica, el código saca los campos
            # exactos del XML. Esto NO pasa por ninguna IA: el formato ya
            # trae cada dato con su nombre.
            "leido": lectura.leer_xml(contenido),
        }

    # --- Hojas de cálculo: se arma una tabla ---
    try:
        filas = importar.leer_archivo(documento["nombre_guardado"], contenido)
    except ValueError as error:
        return {"vista": "sin_vista", "url": direccion, "motivo": str(error)}

    recortado = len(filas) > FILAS_EN_VISTA
    filas_visibles = [
        [importar.texto_de_casilla(casilla) for casilla in fila[:COLUMNAS_EN_VISTA]]
        for fila in filas[:FILAS_EN_VISTA]
    ]

    return {
        "vista": "tabla",
        "url": direccion,
        "filas": filas_visibles,
        "total_filas": len(filas),
        "recortado": recortado,
    }
