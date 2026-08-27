"""
El checklist: qué documentos se le pidieron a cada cliente y cuáles llegaron.

Esta es la parte que responde la pregunta que le duele al contador:
*¿qué le falta a este cliente?*

Dos ideas importantes, y las dos vienen del brief:

  1. **La lista de abajo es una sugerencia, no una regla.** Es el punto de
     partida para una persona natural. El contador agrega y quita renglones
     según lo que de verdad necesite cada cliente.

  2. **El programa no decide nada.** No dice si un documento es obligatorio,
     ni si el cliente está obligado a declarar, ni qué es deducible. Solo
     lleva la cuenta de lo que el contador pidió y de lo que ya recibió.
"""

# Los dos únicos estados que puede tener un renglón.
FALTANTE = "faltante"
RECIBIDO = "recibido"
ESTADOS = (FALTANTE, RECIBIDO)

# Punto de partida para renta de persona natural (sección 9 del brief).
# El contador lo ajusta cliente por cliente.
LISTA_BASE = [
    "Certificado de ingresos y retenciones (uno por empleador)",
    "Certificados bancarios: saldos a 31 de diciembre, intereses, GMF",
    "Certificado de aportes a pensión voluntaria / AFC",
    "Certificado de medicina prepagada",
    "Certificado de intereses de crédito de vivienda",
    "Certificado de dependientes",
    "Certificados de inversiones o acciones",
    "Soportes de bienes inmuebles",
    "Soportes de vehículos",
    "Certificados de retención por honorarios",
    "Otros ingresos y soportes varios",
]


def limpiar_titulo(texto):
    """Deja el nombre del renglón en forma presentable.

    Devuelve el texto limpio, o lanza ValueError con un mensaje que el
    contador pueda entender.
    """
    if texto is None:
        raise ValueError("El renglón no puede estar vacío.")
    limpio = " ".join(str(texto).split())
    if not limpio:
        raise ValueError("El renglón no puede estar vacío.")
    if len(limpio) > 200:
        raise ValueError("El renglón es demasiado largo.")
    return limpio


def limpiar_estado(texto):
    """Verifica que el estado sea uno de los dos que existen."""
    limpio = (texto or "").strip().lower()
    if limpio not in ESTADOS:
        raise ValueError("El estado debe ser 'recibido' o 'faltante'.")
    return limpio
