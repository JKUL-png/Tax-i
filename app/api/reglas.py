"""
Las reglas que el contador enseñó corrigiendo.

Cada vez que él cambia una sugerencia, el programa guarda qué tercero,
qué clase de papel y a qué renglón lo mandó. La próxima vez que llegue
un documento parecido se propone lo que él decidió, y vale para todos
sus clientes.

Son SUYAS: puede verlas todas y borrar la que no le sirva. Un programa
que aprende sin que se pueda ver qué aprendió es un programa en el que
no se puede confiar.

Lo que estas reglas NO guardan: ni el nombre de un cliente, ni el de un
archivo, ni una letra de su contenido. Solo quién emite el documento y a
qué renglón va.
"""

from app import clasificacion, db
from app.api.base import app
from app.servidor import ErrorHttp


@app.get("/api/reglas")
def api_listar_reglas(peticion):
    """Todas las reglas aprendidas, las más usadas primero."""
    salida = []
    for regla in db.listar_reglas():
        regla["frase"] = clasificacion.descripcion_de_regla(regla)
        salida.append(regla)
    return salida


@app.delete("/api/reglas/{id_regla}")
def api_eliminar_regla(peticion, id_regla):
    """Borra una regla. El programa deja de proponer eso."""
    if not db.eliminar_regla(id_regla):
        raise ErrorHttp(404, "Esa regla no existe.")
