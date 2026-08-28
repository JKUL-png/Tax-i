"""
El Formulario 210 de cada cliente.

La plantilla es una sola y es de todos: el archivo con licencia que el
contador dejó en la carpeta plantillas/. Lo que cambia de un cliente a
otro son los valores que se capturan.

Cómo se guarda cada cliente por separado
----------------------------------------
Lo que se guarda en la base de datos NO es el archivo de Excel, son los
valores: "para el cliente 3, en la celda G32 va 1.500.000, y ese dato
salió de tal documento". El archivo de Excel se arma cuando alguien lo
pide, así:

    plantilla limpia  ->  copia nueva  ->  se escriben los valores
    del cliente       ->  se verifica  ->  se calculan los totales

Esto tiene tres ventajas sobre ir editando un archivo por cliente:

  1. Cada archivo sale siempre de la plantilla original, sin tocar. Nunca
     se escribe encima de un archivo que ya se escribió antes, así que no
     se van acumulando reescrituras.
  2. La verificación completa se puede hacer siempre, porque siempre hay
     con qué comparar: la plantilla limpia.
  3. Corregir o quitar un valor es cambiar una fila de la base. El archivo
     se vuelve a armar y ya.

Cada cliente tiene su carpeta en datos/formularios/cliente-N/, y ahí queda
su archivo con su bitácora. El de un cliente nunca se mezcla con el de otro.
"""

import shutil
import unicodedata
from pathlib import Path

from openpyxl import load_workbook

from app import db
from app.documentos import sanitizar_nombre
from app.escribir_210 import EscritorPlantilla, EscrituraBloqueada
from app.plantilla_210 import RAIZ, TIPO_CAPTURA, mapear_plantilla
from app.recalcular import buscar_libreoffice

CARPETA_PLANTILLAS = RAIZ / "plantillas"
CARPETA_FORMULARIOS = RAIZ / "datos" / "formularios"

# El archivo de cada cliente siempre se llama igual dentro de su carpeta.
# El nombre bonito (con el nombre del cliente) se le pone al descargarlo.
NOMBRE_ARCHIVO = "formulario.xlsx"

# Cuántos resultados devuelve una búsqueda de conceptos.
LIMITE_BUSQUEDA = 40

# Cuántos conceptos padre se muestran encima de una casilla, y qué tan
# largo puede ser cada uno. La plantilla tiene títulos larguísimos; en
# pantalla lo que sirve es el rastro corto: "Gastos personales › Ropa".
CUANTOS_PADRES = 2
LARGO_DEL_PADRE = 38

# Secciones cuyos totales NO se muestran en pantalla.
#
# "Liquidación Privada" son los renglones 116 a 137: el impuesto a cargo,
# el anticipo y los saldos a pagar o a favor. Este programa no calcula
# impuestos ni dice cuánto hay que pagar, así que tampoco los muestra en
# pantalla. Están en el archivo de Excel, que es la herramienta del
# contador, y ahí los ve él.
SECCIONES_QUE_NO_SE_MUESTRAN = ("Liquidación Privada",)


class SinPlantilla(Exception):
    """No hay ninguna plantilla en la carpeta plantillas/."""


# ---------------------------------------------------------------------------
# La plantilla y su mapa
# ---------------------------------------------------------------------------


def ruta_plantilla():
    """La plantilla que se va a usar, o None si no hay ninguna.

    Se toma el primer .xlsx de la carpeta plantillas/. Se ignoran los
    archivos que empiezan por ~$ (los temporales que deja Excel abierto).
    """
    if not CARPETA_PLANTILLAS.exists():
        return None
    encontradas = sorted(
        p for p in CARPETA_PLANTILLAS.glob("*.xlsx")
        if not p.name.startswith("~$")
    )
    return encontradas[0] if encontradas else None


# Leer la plantilla y armar el mapa toma un segundo y medio. Se guarda en
# memoria para no repetirlo en cada tecla que el contador escribe en el
# buscador. Si cambia el archivo (otra plantilla, o la misma corregida), la
# fecha de modificación cambia y el mapa se vuelve a armar solo.
_mapa_guardado = {"ruta": None, "modificado": None, "mapa": None, "indice": None}


def mapa():
    """El mapa de celdas de la plantilla, sacado de memoria si ya se leyó."""
    ruta = ruta_plantilla()
    if ruta is None:
        raise SinPlantilla(
            "No hay ninguna plantilla en la carpeta plantillas/."
            " Ponga ahí el archivo de Excel del Formulario 210."
        )

    modificado = ruta.stat().st_mtime
    if (_mapa_guardado["ruta"] != ruta
            or _mapa_guardado["modificado"] != modificado):
        armado = mapear_plantilla(ruta)
        _mapa_guardado.update(
            ruta=ruta,
            modificado=modificado,
            mapa=armado,
            indice={c["celda"]: c for c in armado["celdas"]},
        )
    return _mapa_guardado["mapa"]


def indice():
    """Las celdas del mapa en un diccionario: {'G32': {...}}."""
    mapa()
    return _mapa_guardado["indice"]


def resumen_plantilla():
    """Lo que la pantalla necesita saber sobre la plantilla."""
    ruta = ruta_plantilla()
    if ruta is None:
        return {
            "hay_plantilla": False,
            "motivo": (
                "No hay ninguna plantilla en la carpeta plantillas/. Ponga"
                " ahí el archivo de Excel del Formulario 210 y recargue."
            ),
            "libreoffice": bool(buscar_libreoffice()),
        }

    armado = mapa()
    de_captura = sum(
        1 for c in armado["celdas"] if c["tipo"] == TIPO_CAPTURA
    )
    return {
        "hay_plantilla": True,
        "archivo": ruta.name,
        "hoja": armado["hoja"],
        "celdas_de_captura": de_captura,
        "libreoffice": bool(buscar_libreoffice()),
    }


def buscar_celdas(texto, limite=LIMITE_BUSQUEDA, solo_esperadas=True):
    """Busca conceptos de la plantilla por palabra o por número de renglón.

    Solo devuelve celdas donde se puede escribir.

    Por defecto muestra únicamente las casillas que la plantilla trae con
    un 0 puesto, que son las que el archivo espera que alguien diligencie.
    En una fila hay tres columnas escribibles (subparcial, parcial y total)
    y casi siempre el dato va en una sola; mostrar las tres confunde más de
    lo que ayuda. Con solo_esperadas=False se ven todas, para el caso raro
    en que el contador necesite otra.
    """
    texto = _sin_tildes(texto).strip()
    encontradas = []

    for celda in mapa()["celdas"]:
        if celda["tipo"] != TIPO_CAPTURA:
            continue
        if solo_esperadas and not celda["cero_precargado"]:
            continue
        if texto:
            en_descripcion = texto in _sin_tildes(celda["descripcion"])
            en_contexto = any(
                texto in _sin_tildes(c) for c in (celda.get("contexto") or [])
            )
            en_renglon = texto == celda["renglon"]
            en_celda = texto == celda["celda"].lower()
            en_seccion = texto in _sin_tildes(celda["seccion"])
            if not (en_descripcion or en_contexto or en_renglon or en_celda
                    or en_seccion):
                continue
        encontradas.append(celda)

    encontradas.sort(
        key=lambda c: (not c["cero_precargado"], c["fila"], c["columna"])
    )
    return [_para_pantalla(c) for c in encontradas[:limite]]


def _sin_tildes(texto):
    """'Alimentación' -> 'alimentacion', para poder buscar sin tildes.

    El contador escribe rápido y no siempre pone las tildes. Que la
    búsqueda no le sirva por eso sería absurdo.
    """
    sin_marcas = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in sin_marcas if unicodedata.category(c) != "Mn")


def _rastro(contexto):
    """Los conceptos padre, cortos y en una sola línea.

    Los títulos de la plantilla son larguísimos y casi siempre la parte
    útil está antes del primer paréntesis o de la primera coma:

        "Gastos personales (incluido el IVA o INC que…)" -> "Gastos personales"

    Si cortar por ahí deja algo demasiado corto, se recorta a lo bruto.
    """
    cortos = []
    for texto in (contexto or [])[-CUANTOS_PADRES:]:
        for signo in ("(", ";", ":", ","):
            if signo in texto:
                antes = texto.split(signo)[0].strip()
                if len(antes) >= 12:
                    texto = antes
                    break
        if len(texto) > LARGO_DEL_PADRE:
            texto = texto[:LARGO_DEL_PADRE].rstrip(" ,;:(") + "…"
        cortos.append(texto)
    return " › ".join(cortos)


def _para_pantalla(celda):
    """Deja de una celda del mapa solo lo que la pantalla usa."""
    return {
        "celda": celda["celda"],
        "columna": celda["columna"],
        "fila": celda["fila"],
        "descripcion": celda["descripcion"],
        # De qué conceptos cuelga: "Gastos personales › Alimentación".
        "contexto": _rastro(celda.get("contexto")),
        "seccion": celda["seccion"],
        "renglon": celda["renglon"],
        "esperado": celda["cero_precargado"],
    }


# ---------------------------------------------------------------------------
# Los valores de cada cliente
# ---------------------------------------------------------------------------


def guardar_valor(cliente_id, celda, valor, documento=""):
    """Guarda un valor para un cliente, después de revisar que se pueda.

    Esta es la puerta por la que entran los datos, vengan de donde vengan:
    del contador escribiéndolos a mano o de la lectura de un documento. La
    revisión es la misma para todos.
    """
    celda = str(celda).upper().strip()
    informacion = indice().get(celda)

    if informacion is None:
        raise EscrituraBloqueada(
            f"La celda {celda} no existe en la hoja de captura de la"
            f" plantilla."
        )
    if informacion["tipo"] != TIPO_CAPTURA:
        motivo = informacion["motivo"] or "no es una casilla de captura"
        raise EscrituraBloqueada(
            f"En {celda} no se puede escribir: {motivo}."
        )
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise EscrituraBloqueada(
            "El valor tiene que ser un número. Para dejar una casilla en"
            " cero, escriba 0."
        )
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise EscrituraBloqueada("Ese número no se puede guardar.")

    guardado = db.guardar_valor_210(cliente_id, celda, valor, documento)
    guardado.update(_para_pantalla(informacion))
    guardado["valor"] = db._numero(valor)
    return guardado


def listar_valores(cliente_id):
    """Los valores capturados de un cliente, con la descripción de cada uno."""
    capturados = db.listar_valores_210(cliente_id)
    catalogo = indice()

    salida = []
    for celda, guardado in capturados.items():
        informacion = catalogo.get(celda)
        fila = dict(guardado)
        if informacion is not None:
            fila.update(_para_pantalla(informacion))
        else:
            # La plantilla cambió y esa celda ya no existe. Se muestra
            # igual, para que el contador se entere en vez de que el dato
            # desaparezca en silencio.
            fila.update({
                "descripcion": "Esta celda ya no existe en la plantilla",
                "contexto": "", "seccion": "", "renglon": "", "esperado": False,
                "columna": "", "fila": 0,
            })
        salida.append(fila)

    salida.sort(key=lambda f: (f.get("fila") or 0, f.get("columna") or ""))
    return salida


# ---------------------------------------------------------------------------
# El archivo de cada cliente
# ---------------------------------------------------------------------------


def carpeta_cliente(cliente_id):
    """datos/formularios/cliente-3/ — la carpeta propia de ese cliente."""
    return CARPETA_FORMULARIOS / f"cliente-{int(cliente_id)}"


def archivo_cliente(cliente_id):
    """La ruta del archivo generado de un cliente (exista o no todavía)."""
    return carpeta_cliente(cliente_id) / NOMBRE_ARCHIVO


def nombre_para_descargar(cliente):
    """El nombre con el que se descarga: 'Formulario 210 - Juan Pérez.xlsx'."""
    nombre = (cliente["nombre"] or "cliente").strip()
    return sanitizar_nombre(f"Formulario 210 - {nombre}.xlsx")


def eliminar_carpeta_cliente(cliente_id):
    """Borra la carpeta del cliente. Se llama al eliminar el cliente."""
    carpeta = carpeta_cliente(cliente_id)
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)


def estado(cliente_id):
    """En qué va el formulario de un cliente: cuántos valores, qué archivo hay."""
    archivo = archivo_cliente(cliente_id)
    cuantos = len(db.listar_valores_210(cliente_id))

    if not archivo.exists():
        return {"valores": cuantos, "hay_archivo": False}

    from datetime import datetime
    generado = datetime.fromtimestamp(archivo.stat().st_mtime)
    return {
        "valores": cuantos,
        "hay_archivo": True,
        "generado": generado.isoformat(timespec="seconds"),
        "tamano": archivo.stat().st_size,
    }


def leer_totales(ruta_xlsx):
    """Lee los totales que quedaron calculados en el archivo.

    Devuelve un renglón por cada total del formulario, con su número, su
    descripción y su valor. Solo sirve si el archivo pasó por el recálculo:
    si no, los totales están sin calcular y no se devuelve ninguno.

    Los renglones de la liquidación privada (impuesto y saldos) no entran:
    ver SECCIONES_QUE_NO_SE_MUESTRAN.
    """
    libro = load_workbook(Path(ruta_xlsx), data_only=True)
    hoja = libro[mapa()["hoja"]]

    totales = []
    vistos = set()
    for celda in mapa()["celdas"]:
        if celda["columna"] != "I" or not celda["renglon"]:
            continue
        if celda["seccion"] in SECCIONES_QUE_NO_SE_MUESTRAN:
            continue
        if celda["renglon"] in vistos:
            continue
        valor = hoja[celda["celda"]].value
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            continue
        vistos.add(celda["renglon"])
        totales.append({
            "renglon": celda["renglon"],
            "descripcion": celda["descripcion"],
            "seccion": celda["seccion"],
            "valor": int(valor) if float(valor).is_integer() else float(valor),
        })

    totales.sort(key=lambda t: int(t["renglon"]))
    return totales


def generar(cliente):
    """Arma el archivo de Excel de un cliente y devuelve cómo salió.

    Siempre parte de la plantilla limpia y le escribe todos los valores
    capturados de ese cliente. El archivo anterior de ese cliente se
    reemplaza; los de los demás clientes ni se tocan.
    """
    plantilla = ruta_plantilla()
    if plantilla is None:
        raise SinPlantilla(
            "No hay ninguna plantilla en la carpeta plantillas/."
        )

    cliente_id = cliente["id"]
    valores = db.listar_valores_210(cliente_id)

    escritor = EscritorPlantilla(
        plantilla,
        nombre_salida=NOMBRE_ARCHIVO,
        carpeta_trabajo=carpeta_cliente(cliente_id),
    )
    for celda, guardado in valores.items():
        escritor.escribir(
            celda,
            guardado["valor"],
            documento=guardado["documento"] or "digitado por el contador",
        )

    ruta, ruta_bitacora = escritor.guardar()

    informe = {
        "archivo": str(ruta.relative_to(RAIZ)),
        "nombre_descarga": nombre_para_descargar(cliente),
        "valores_escritos": len(valores),
        "verificacion": escritor.informe_verificacion,
        "recalculo": escritor.informe_recalculo,
        "bitacora": str(ruta_bitacora.relative_to(RAIZ)),
        "totales": [],
    }
    if escritor.informe_recalculo and escritor.informe_recalculo["recalculado"]:
        informe["totales"] = leer_totales(ruta)

    return informe
