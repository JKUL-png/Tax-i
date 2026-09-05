"""
La pasada del formulario: pedirla, revisarla, aprobarla y medirla.

Una llamada al modelo por cliente, con toda su exógena y todos sus
documentos adentro, y sale la propuesta completa del Formulario 210.

Lo que estas direcciones NO hacen, y no es un detalle:

  - No escriben nada en el formulario del cliente hasta que él aprueba.
    La propuesta vive en su propia tabla; el 210 sigue intacto.
  - No aprueban solas, ni siquiera lo de nivel A. Aprobar en bloque
    muestra la lista antes de confirmar.
  - No corren solas al subir documentos. Leer con IA cuesta plata, y esa
    decisión es del contador. Es la regla de la casa: lo que es gratis y
    pasa en este computador ocurre sin pedir permiso; lo que cuesta lo
    pide él.
"""

from pathlib import Path

from app import comparacion, cruce, db, documentos, formulario, pasada
from app.api.base import app, cliente_o_404
from app.escribir_210 import EscrituraBloqueada
from app.servidor import ErrorHttp

RAIZ = Path(__file__).resolve().parent.parent.parent
CARPETA_COMPARACION = RAIZ / "datos" / "comparacion"

EXTENSIONES = (".xlsx", ".xlsm")


def _ids(datos, campo="ids"):
    crudos = datos.get(campo)
    if not isinstance(crudos, list) or not crudos:
        raise ErrorHttp(400, "No se escogió ninguna propuesta.")
    try:
        return [int(uno) for uno in crudos]
    except (TypeError, ValueError):
        raise ErrorHttp(400, "Alguna de las propuestas no se entendió.")


@app.get("/api/clientes/{id_cliente}/pasada")
def api_pasada(peticion, id_cliente):
    """La propuesta vigente de un cliente, agrupada por renglón."""
    cliente_o_404(id_cliente)
    return pasada.resumen(id_cliente)


@app.get("/api/clientes/{id_cliente}/pasada/estimado")
def api_estimado(peticion, id_cliente):
    """Cuánto va a costar la pasada, ANTES de correrla.

    Se le dice antes de gastar, no después. El número es una estimación
    a partir del texto que se va a mandar; el de verdad lo dice el
    servicio y queda guardado en la pantalla de Cuenta.
    """
    cliente = cliente_o_404(id_cliente)
    from app.configuracion import CONFIG
    from app import proveedores

    try:
        entrada = pasada.armar_entrada(cliente)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(400, str(error))

    tokens = pasada.tokens_estimados(entrada)
    ficha = proveedores.obtener(CONFIG.proveedor)
    return {
        "ia_disponible": CONFIG.ia_disponible,
        "motivo": CONFIG.motivo,
        "documentos": entrada["documentos"],
        "filas_exogena": entrada["filas_exogena"],
        "sin_texto": entrada["sin_texto"],
        "bloques": len(entrada["bloques"]),
        "tokens_estimados": tokens,
        # Aproximado, y se dice que es aproximado en la pantalla.
        "costo_estimado": ficha.costo_en_dolares(
            {"entrada": tokens, "salida": 4000}
        ),
        "modelo": CONFIG.modelo,
    }


@app.post("/api/clientes/{id_cliente}/pasada")
def api_correr(peticion, id_cliente, **partes):
    """Le pide al modelo la propuesta del formulario de este cliente."""
    cliente = cliente_o_404(id_cliente)
    try:
        return pasada.correr(cliente)
    except pasada.SinIA as error:
        raise ErrorHttp(409, str(error))
    except pasada.PasadaEnCurso as error:
        # 409: el pedido está bien hecho, pero ahora mismo no cabe. Lo
        # importante es que aquí NO se llamó al modelo y no se gastó nada.
        raise ErrorHttp(409, str(error))
    except pasada.PasadaFallida as error:
        raise ErrorHttp(502, str(error))


@app.put("/api/pasada/automatico")
def api_automatico(peticion, **partes):
    """Prende o apaga el pedir la propuesta al confirmar una carga.

    Viene APAGADO de fábrica. La pasada cuesta plata y esa decisión es
    del contador, no del programa.
    """
    datos = peticion.diccionario()
    if "prendido" not in datos:
        raise ErrorHttp(400, "Falta decir si se prende o se apaga.")
    return {"automatico": pasada.cambiar_automatico(bool(datos["prendido"]))}


@app.get("/api/clientes/{id_cliente}/pasada/en-bloque")
def api_en_bloque(peticion, id_cliente):
    """Lo que se aprobaría en bloque, para verlo ANTES de confirmar.

    Aceptar veinte propuestas a ciegas es justo el error que este
    programa no debe dejar cometer.
    """
    cliente_o_404(id_cliente)
    valores = pasada.para_aprobar_en_bloque(id_cliente)
    return {
        "valores": valores,
        "cuantos": len(valores),
        "renglones": sorted({v["renglon"] for v in valores}),
    }


@app.post("/api/clientes/{id_cliente}/pasada/aprobar")
def api_aprobar(peticion, id_cliente, **partes):
    """Pasa al Formulario 210 las propuestas que él escogió."""
    cliente = cliente_o_404(id_cliente)
    ids = _ids(peticion.diccionario())
    try:
        resultado = pasada.aprobar(cliente, ids)
    except pasada.PasadaFallida as error:
        raise ErrorHttp(400, str(error))
    except EscrituraBloqueada as error:
        raise ErrorHttp(400, str(error))
    resultado["pasada"] = pasada.resumen(id_cliente)
    return resultado


@app.post("/api/clientes/{id_cliente}/pasada/descartar")
def api_descartar(peticion, id_cliente, **partes):
    """Descarta propuestas. No se borran: queda el rastro de que existieron."""
    cliente_o_404(id_cliente)
    cuantas = pasada.descartar(id_cliente, _ids(peticion.diccionario()))
    return {"descartadas": cuantas, "pasada": pasada.resumen(id_cliente)}


@app.get("/api/clientes/{id_cliente}/pasada/casillas")
def api_casillas_del_renglon(peticion, id_cliente):
    """Las casillas donde se puede escribir un renglón, para que él escoja.

    Un renglón NO es una casilla: R33 son siete filas de detalle en la
    plantilla. Cuando ninguna gana claramente, el programa no adivina —
    escribir una cifra en la fila equivocada de su declaración es un
    daño de verdad— y le muestra las opciones con la etiqueta que trae
    cada fila, que es lo que le permite reconocerla.

    Solo salen las casillas que alguna fórmula LEE. Ofrecer una de las
    otras sería ofrecer un error silencioso: la cifra queda escrita,
    parece anotada, y el renglón se queda en cero.
    """
    cliente_o_404(id_cliente)
    codigo = (peticion.consulta.get("renglon") or "").strip()
    numero = codigo.upper().lstrip("R")
    if not numero.isdigit():
        raise ErrorHttp(400, "Falta decir de cuál renglón.")

    try:
        casillas = formulario.celdas_de_renglon(numero)
        recordada = formulario.casilla_recordada(numero)
    except formulario.SinPlantilla as error:
        raise ErrorHttp(409, str(error))

    return {
        "renglon": "R" + numero,
        "casillas": casillas,
        "recordada": recordada,
        # Cuando no hay ninguna, la plantilla no tiene dónde escribir ese
        # renglón. Se dice, en vez de mostrar una lista vacía.
        "motivo": "" if casillas else (
            "En esta plantilla, el renglón R%s no tiene ninguna casilla"
            " que alguna fórmula lea. Anótelo directamente en la hoja de"
            " captura si su plantilla lo maneja de otra forma." % numero
        ),
    }


@app.put("/api/clientes/{id_cliente}/pasada/casilla")
def api_casilla(peticion, id_cliente, **partes):
    """El contador escoge la casilla cuando el programa no pudo."""
    cliente_o_404(id_cliente)
    datos = peticion.diccionario()
    try:
        return pasada.cambiar_casilla(
            id_cliente, datos.get("id"), datos.get("celda")
        )
    except pasada.PasadaFallida as error:
        raise ErrorHttp(400, str(error))


@app.get("/api/clientes/{id_cliente}/cruce")
def api_cruce(peticion, id_cliente):
    """Lo que dicen sus papeles contra lo que reportó la DIAN.

    Sin IA y sin costo: son dos listas de números que ya están en la
    base y una resta. Se compara por RENGLÓN, que es lo único que se
    puede afirmar sin suponer cuál fila de la exógena corresponde a cuál
    papel. Ver app/cruce.py.
    """
    cliente_o_404(id_cliente)
    return cruce.revisar(id_cliente)


# ----------------------------------------------------------
# El modo comparación
# ----------------------------------------------------------


@app.get("/api/clientes/{id_cliente}/comparacion")
def api_comparacion(peticion, id_cliente):
    """La última medición de este cliente, si ya se hizo alguna."""
    cliente_o_404(id_cliente)
    return comparacion.ultima(id_cliente) or {"hay_comparacion": False}


@app.post("/api/clientes/{id_cliente}/comparacion", codigo=201)
def api_comparar(peticion, id_cliente, **partes):
    """Compara la propuesta contra el 210 que el contador ya llenó.

    Es una medición: no cambia ni una cifra del cliente.
    """
    cliente = cliente_o_404(id_cliente)

    archivos = peticion.archivos("archivo")
    if not archivos:
        raise ErrorHttp(400, "No llegó ningún archivo.")
    nombre_original, contenido = archivos[0]

    if Path(nombre_original).suffix.lower() not in EXTENSIONES:
        raise ErrorHttp(
            400,
            "Para comparar hace falta el Formulario 210 lleno, en Excel"
            " (.xlsx). Ese archivo es %s."
            % (Path(nombre_original).suffix or "de otro tipo"),
        )

    carpeta = CARPETA_COMPARACION / str(id_cliente)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = documentos.nombre_libre(
        carpeta, documentos.sanitizar_nombre(nombre_original)
    )
    destino = carpeta / nombre
    destino.write_bytes(contenido)

    try:
        informe = comparacion.comparar(cliente, destino, nombre)
    except comparacion.ComparacionInvalida as error:
        destino.unlink(missing_ok=True)
        raise ErrorHttp(400, str(error))
    informe["hay_comparacion"] = True
    return informe


# ----------------------------------------------------------
# Lo que se ha gastado
# ----------------------------------------------------------


@app.get("/api/gasto")
def api_gasto(peticion):
    """Tokens y costo aproximado, por cliente y acumulado."""
    return {
        "total": db.gasto_de_pasadas(),
        "por_cliente": db.gasto_por_cliente(),
        "aviso": (
            "El costo es aproximado: sale de la lista de precios que trae"
            " el programa, que tiene fecha. Los tokens sí son los que"
            " reportó el servicio."
        ),
    }
