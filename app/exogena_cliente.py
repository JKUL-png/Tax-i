"""
La exógena de un cliente: sus renglones y su tabla.

app/exogena.py lee el archivo y ya. Este archivo es el que hace algo con
lo leído: le crea al cliente los renglones que la DIAN menciona y arma
la tabla que se ve en la pestaña Exógena.

Dos reglas mandan aquí, y las dos son del contador:

  1. **Nunca se borra un renglón que tenga documentos encima.** Volver a
     cargar la exógena reemplaza los registros reportados, pero los
     renglones se quedan. Si el archivo nuevo ya no menciona uno, se
     avisa y él decide; borrarle en octubre un renglón con soportes
     asignados es un daño real.

  2. **Nada se agrega solo, salvo los renglones de la DIAN.** Y esos no
     los inventa nadie: salen del archivo oficial, con el nombre que la
     propia DIAN les da.

Y una que es del proyecto: aquí tampoco hay IA. Las comparaciones de
cifras las hace el código, con las cifras que ya se leyeron una vez y
viven en la tabla datos_extraidos.
"""

import re
import shutil
from pathlib import Path

from app import bitacora, db, exogena

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_EXOGENA = RAIZ / "datos" / "exogena"

# Los estados de la tabla. Están escritos como los diría el contador:
# "Sin soporte" es que falta el papel, NO que haya que declararlo.
# "Diferencia" es revíselo, NO que esté mal.
COINCIDE = "coincide"
DIFERENCIA = "diferencia"
SIN_SOPORTE = "sin_soporte"
SIN_COMPARAR = "sin_comparar"
SIN_REPORTAR = "sin_reportar"
REQUIERE_DECISION = "requiere_decision"
POSIBLE_DUPLICADO = "posible_duplicado"

ESTADOS = {
    COINCIDE: "Coincide",
    DIFERENCIA: "Diferencia",
    SIN_SOPORTE: "Sin soporte",
    SIN_COMPARAR: "Sin comparar",
    SIN_REPORTAR: "Sin reportar",
    REQUIERE_DECISION: "Requiere decisión",
    POSIBLE_DUPLICADO: "Posible duplicado",
}

# En qué orden se muestra el estado cuando una fila cae en varios. La
# fila igual queda marcada con todos, para que el filtro la encuentre
# por cualquiera de ellos.
PRIORIDAD = [REQUIERE_DECISION, POSIBLE_DUPLICADO, DIFERENCIA,
             SIN_COMPARAR, SIN_SOPORTE, SIN_REPORTAR, COINCIDE]

# Dos cifras se dan por iguales si se diferencian en menos de un peso.
# No es una tolerancia contable: es para que 2460998.0 y 2460998 no
# salgan como diferentes por ser uno decimal y el otro entero.
TOLERANCIA = 1.0


# ----------------------------------------------------------
# Leer una cifra escrita como se escribe en Colombia
# ----------------------------------------------------------


def cifra(texto):
    """Convierte «$ 2.460.998,50» en 2460998.5. Devuelve None si no es cifra.

    En Colombia el punto separa los miles y la coma los decimales, al
    revés que en inglés. Se resuelve mirando la forma del número, no
    adivinando:

      - Si tiene coma Y punto, el último que aparece es el decimal.
      - Si solo tiene puntos y el último grupo es de tres dígitos, son
        miles: «2.460.998».
      - Si solo tiene coma, es decimal.

    Esto NO calcula nada: solo lee un número que ya estaba escrito.
    """
    if texto is None:
        return None
    if isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        return float(texto)

    limpio = str(texto).strip()
    # Fuera todo lo que no sea dígito, separador o signo.
    limpio = re.sub(r"[^\d.,\-]", "", limpio)
    if not re.search(r"\d", limpio):
        return None

    negativo = limpio.startswith("-")
    limpio = limpio.lstrip("-")

    tiene_punto = "." in limpio
    tiene_coma = "," in limpio

    if tiene_punto and tiene_coma:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif tiene_coma:
        # Una sola coma con uno o dos dígitos detrás es un decimal;
        # cualquier otra cosa son miles.
        if re.fullmatch(r"\d+,\d{1,2}", limpio):
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif tiene_punto:
        # «2.460.998» son miles. «2460.5» es un decimal.
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", limpio):
            limpio = limpio.replace(".", "")

    try:
        numero = float(limpio)
    except ValueError:
        return None
    return -numero if negativo else numero


# ----------------------------------------------------------
# Crear los renglones que la DIAN menciona
# ----------------------------------------------------------


def sincronizar_renglones(cliente_id, lectura):
    """Le crea al cliente los renglones del 210 que la exógena menciona.

    Devuelve qué pasó, para contárselo al contador:

      creados     — los que no tenía y ahora sí
      ya_estaban  — los que ya tenía, que no se tocan
      huerfanos   — renglones de una carga anterior que este archivo ya
                    no menciona. NO se borran: se avisan y él decide.
    """
    existentes = db.listar_checklist(cliente_id)
    por_codigo = {
        r["codigo_renglon"]: r for r in existentes if r.get("codigo_renglon")
    }

    creados = []
    ya_estaban = []
    for renglon in exogena.catalogo_de_renglones(lectura):
        # "R32" se guarda como "32": es el número del renglón del 210,
        # que es como lo conoce la plantilla del contador.
        codigo = renglon["codigo"][1:]
        if codigo in por_codigo:
            ya_estaban.append(por_codigo[codigo])
            continue
        creado = db.crear_renglon(
            cliente_id, renglon["titulo"],
            codigo_renglon=codigo, origen="dian",
        )
        creados.append(creado)

    mencionados = {r["codigo"][1:] for r in exogena.catalogo_de_renglones(lectura)}
    con_documentos = db.contar_documentos_por_renglon(cliente_id)
    huerfanos = []
    for renglon in existentes:
        codigo = renglon.get("codigo_renglon") or ""
        if renglon.get("origen") != "dian" or not codigo:
            continue
        if codigo in mencionados:
            continue
        huerfanos.append({
            "id": renglon["id"],
            "titulo": renglon["titulo"],
            "documentos": con_documentos.get(renglon["id"], 0),
        })

    if creados:
        bitacora.anotar(cliente_id, bitacora.RENGLON_AGREGADO,
                        "renglones de la exógena", len(creados))

    return {"creados": creados, "ya_estaban": ya_estaban, "huerfanos": huerfanos}


def cargar(cliente_id, ruta_archivo, nombre_archivo=""):
    """Lee el archivo de exógena, lo guarda y crea los renglones.

    Si ya había exógena de ese mismo año, la reemplaza: la DIAN advierte
    que la información cambia cuando un tercero la modifica después, así
    que el archivo nuevo manda. Los renglones NO se reemplazan.
    """
    lectura = exogena.leer(ruta_archivo)
    anio = lectura["cabecera"].get("anio") or ""
    habia = db.obtener_carga_exogena(cliente_id, anio) is not None

    carga = db.guardar_exogena(cliente_id, lectura, nombre_archivo)
    cambios = sincronizar_renglones(cliente_id, lectura)

    bitacora.anotar(
        cliente_id,
        bitacora.EXOGENA_REEMPLAZADA if habia else bitacora.EXOGENA_CARGADA,
        nombre_archivo, len(lectura["filas"]),
    )

    # Ahora hay con qué cruzar los documentos: la exógena trae el NIT y
    # el nombre de cada tercero, con su renglón. Los que estaban sin
    # asignar se vuelven a mirar. Los que el contador ya asignó a mano
    # no se tocan: su decisión manda sobre cualquier sugerencia.
    from app import clasificacion
    db.marcar_para_clasificar(cliente_id)
    clasificacion.arrancar(cliente_id)

    return {
        "carga": carga,
        "resumen": exogena.resumen(lectura),
        "reemplazo": habia,
        "renglones": {
            "creados": len(cambios["creados"]),
            "ya_estaban": len(cambios["ya_estaban"]),
            "huerfanos": cambios["huerfanos"],
        },
    }


# ----------------------------------------------------------
# Armar la tabla de la pestaña
# ----------------------------------------------------------


def _cifras_del_documento(extraidos, documento_id):
    """Las cifras que se le leyeron a un documento, ya como números."""
    cifras = []
    for dato in extraidos:
        if dato["documento_id"] != documento_id:
            continue
        numero = cifra(dato["valor"])
        if numero is None:
            continue
        cifras.append({
            "concepto": dato["concepto"],
            "valor": numero,
            "escrito": dato["valor"],
            "origen": dato["origen"],
        })
    return cifras


def _comparar(valor_dian, cifras):
    """Compara la cifra de la DIAN con las del soporte.

    Devuelve (estado, la cifra del soporte que se usó). Busca primero
    una que cuadre; si ninguna cuadra, se queda con la más parecida para
    poder mostrar las dos cifras, que es lo que pide el contador.

    No suma, no promedia y no corrige: solo compara.
    """
    if not cifras:
        return SIN_COMPARAR, None
    if valor_dian is None:
        return SIN_COMPARAR, None

    iguales = [c for c in cifras if abs(c["valor"] - valor_dian) <= TOLERANCIA]
    if iguales:
        return COINCIDE, iguales[0]

    mas_cercana = min(cifras, key=lambda c: abs(c["valor"] - valor_dian))
    return DIFERENCIA, mas_cercana


def _sugerir_soporte(fila, documentos, extraidos):
    """Propone un documento para una fila, por el NIT de quien reporta.

    Es una sugerencia por código, no una asignación: se busca el NIT del
    tercero entre lo que ya se le leyó a cada documento. El contador
    confirma. Si no hay nada claro, no se propone nada.
    """
    nit = (fila.get("nit_reporta") or "").strip()
    if len(nit) < 6:
        return None

    for dato in extraidos:
        texto = "%s %s" % (dato.get("detalle") or "", dato.get("valor") or "")
        if nit not in texto:
            continue
        documento = documentos.get(dato["documento_id"])
        if documento:
            return {"id": documento["id"],
                    "nombre": documento["nombre_original"]}
    return None


def tabla(cliente_id, anio=None):
    """Arma todo lo que la pestaña Exógena necesita mostrar.

    Devuelve la carga (con los avisos de la DIAN y la fecha de corte),
    los cinco topes, las filas con su estado, y los renglones del
    contador que la exógena no menciona.
    """
    carga = db.obtener_carga_exogena(cliente_id, anio)
    renglones = db.listar_checklist(cliente_id)
    documentos = {d["id"]: d for d in db.listar_documentos(cliente_id)}
    extraidos = db.listar_datos_extraidos(cliente_id)
    por_renglon = db.contar_documentos_por_renglon(cliente_id)

    if not carga:
        # Un cliente sin exógena no arranca con nada: sus renglones son
        # los que él haya escrito, y no se le inventa ninguno.
        return {
            "hay_exogena": False,
            "carga": None,
            "topes": [],
            "filas": [],
            "sin_reportar": _sin_reportar(renglones, por_renglon, set()),
            "conteos": {},
            "anios": db.listar_cargas_exogena(cliente_id),
        }

    filas = []
    codigos_usados = set()

    for fila in db.listar_filas_exogena(carga["id"]):
        marcas = []

        # La decisión del contador manda: mientras no elija, la fila
        # queda esperando. El programa no elige por él ni con IA, ni con
        # reglas, ni mirando el signo del valor.
        if fila["requiere_decision"] and not fila["renglon_elegido"]:
            marcas.append(REQUIERE_DECISION)
        if fila["posible_duplicado"]:
            marcas.append(POSIBLE_DUPLICADO)

        cifras = _cifras_del_documento(extraidos, fila["documento_id"])
        if not fila["documento_id"]:
            marcas.append(SIN_SOPORTE)
            comparacion = None
        else:
            estado_cifra, comparacion = _comparar(fila["valor"], cifras)
            marcas.append(estado_cifra)

        fila["marcas"] = marcas
        fila["estado"] = next(e for e in PRIORIDAD if e in marcas)
        fila["estado_texto"] = ESTADOS[fila["estado"]]
        fila["cifra_soporte"] = comparacion
        fila["sugerencia"] = (
            None if fila["documento_id"]
            else _sugerir_soporte(fila, documentos, extraidos)
        )

        # A qué renglón va: el que eligió el contador si eligió, o el
        # único que la DIAN propone si solo propone uno.
        if fila["renglon_elegido"]:
            fila["renglon"] = fila["renglon_elegido"]
        elif len(fila["renglones"]) == 1:
            fila["renglon"] = fila["renglones"][0]["codigo"]
        else:
            fila["renglon"] = ""

        # Un renglón queda "sin reportar" solo si NINGÚN registro lo
        # menciona. Los que la DIAN nombra dentro de una fila que
        # todavía requiere decisión sí están reportados: lo que falta
        # es que el contador decida, y eso ya se ve en esa fila.
        for mencionado in fila["renglones"]:
            codigos_usados.add(mencionado["codigo"][1:])

        filas.append(fila)

    conteos = {}
    for fila in filas:
        for marca in fila["marcas"]:
            conteos[marca] = conteos.get(marca, 0) + 1

    sin_reportar = _sin_reportar(renglones, por_renglon, codigos_usados)
    if sin_reportar:
        conteos[SIN_REPORTAR] = len(sin_reportar)

    return {
        "hay_exogena": True,
        "carga": carga,
        "topes": carga["topes"],
        "filas": filas,
        "sin_reportar": sin_reportar,
        "conteos": conteos,
        "anios": db.listar_cargas_exogena(cliente_id),
    }


def _sin_reportar(renglones, documentos_por_renglon, codigos_usados):
    """Los renglones del cliente de los que la exógena no dice nada.

    No significa que falte nada ni que esté mal: significa que ese
    renglón lo puso el contador y ningún tercero reportó algo que la
    DIAN haya mandado allí.
    """
    sueltos = []
    for renglon in renglones:
        codigo = renglon.get("codigo_renglon") or ""
        if codigo and codigo in codigos_usados:
            continue
        sueltos.append({
            "id": renglon["id"],
            "titulo": renglon["titulo"],
            "codigo_renglon": codigo,
            "origen": renglon.get("origen") or "contador",
            "estado": renglon["estado"],
            "documentos": documentos_por_renglon.get(renglon["id"], 0),
        })
    return sueltos


def eliminar_carpeta_cliente(cliente_id):
    """Borra del disco los archivos de exógena de un cliente.

    Se llama al eliminar el cliente. Las filas de la base se van solas
    (ON DELETE CASCADE), pero el Excel que descargó de la DIAN hay que
    borrarlo a mano: es información tributaria de un tercero y no se
    puede quedar ahí después de eliminar al cliente.
    """
    carpeta = CARPETA_EXOGENA / str(cliente_id)
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)
