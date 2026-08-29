# Cómo probar Tax-i en el computador con Windows

## La respuesta corta

**No se puede probar el programa con un archivo suelto.** El programa es la
carpeta entera: el servidor, las pantallas y la base de datos trabajan juntos.
Lo que se lleva al Windows es el proyecto.

Pero tampoco se copia todo tal como está. Hay dos carpetas que **no** deben
viajar, y copiarlas es peor que no copiar nada:

| Qué | Por qué no va |
|---|---|
| `.venv/` | Son programas compilados para Mac, con rutas del Mac escritas adentro. En Windows no sirven y además tapan el entorno bueno que arma `iniciar.bat`. |
| `datos/` | Son documentos tributarios de clientes de verdad. No tienen por qué estar en dos computadores, y allá se crea sola y vacía. |
| `.env` | Lleva la llave de la IA. Si se quiere llevar, se copia aparte y a mano. Si no, allá se pone desde la pantalla de Cuenta. |

Entonces son dos cosas distintas, y las dos hacen falta:

1. **Llevar el proyecto** (sin esas carpetas).
2. **Saber si funcionó** una vez esté allá — y para eso sí hay un archivo
   aparte: `pruebas/revisar_windows.py`.

---

## 1. Llevar el proyecto

**Si el computador con Windows tiene git** (lo más limpio):

```
git clone <la dirección del repositorio>
```

**Si no tiene git**, aquí en el Mac se arma el paquete con un comando. Este
empaca únicamente lo que está en git, así que deja por fuera `.venv/`,
`datos/` y `.env` sin que haya que acordarse:

```
git archive --format=zip --output=tax-i.zip HEAD
```

Ese `tax-i.zip` es el que se manda o se pasa en una memoria USB. Allá se
descomprime en una carpeta corta, por ejemplo `C:\tax-i`.

> Una carpeta corta importa: Windows corta las rutas a los 260 caracteres, y
> los documentos de los clientes quedan varias carpetas más adentro. Metido
> en `C:\Users\...\OneDrive\Escritorio\Cosas\...` se llega al tope y empiezan
> los errores raros al guardar.

---

## 2. Prenderlo la primera vez

Doble clic en **`iniciar.bat`**.

La primera vez se demora un minuto o dos: arma el entorno y baja las
librerías. Cuando aparezca la dirección, se abre en el navegador:

```
http://localhost:8000
```

Si se cierra sola sin decir nada, casi siempre es que falta Python. Se baja de
python.org y **hay que marcar la casilla "Add Python to PATH"** durante la
instalación.

---

## 3. Saber si de verdad funciona

Apague el servidor con `Control + C`. En esa misma ventana, pegue:

```
.venv\Scripts\python.exe pruebas\revisar_windows.py
```

Eso revisa, una por una, las cosas que funcionan en el Mac y fallan en
Windows, y termina diciendo cuántas pasaron:

- Que la consola escriba tildes y eñes sin romperse.
- Que `iniciar.bat` tenga los saltos de línea que `cmd.exe` necesita.
- Que un archivo llamado `Certificado 2025: Bancolombia.pdf` **se pueda crear
  de verdad** allá, no solo que el nombre se vea bien.
- Que un ZIP hecho con el Explorador de Windows no convierta `Niño.pdf` en
  `Ni├▒o.pdf`.
- Que se pueda escribir en `datos/` (en algunas carpetas de Windows no se
  puede) y que SQLite devuelva las tildes intactas.
- Que el servidor prenda de verdad y conteste las cuatro pantallas.

Si todo pasa, dice **"Todo bien"** y no hay nada más que hacer. Si algo falla,
cada línea que dice `FALLA` explica cuál es; con mandar esa pantalla completa
alcanza para arreglarlo.

El revisor no toca ningún documento ni ningún cliente. Lo único que escribe
son archivos de prueba en una carpeta temporal, que borra al terminar.

---

## 4. Poner la llave de la IA allá

Ya no hay que editar el archivo `.env` con el bloc de notas. En el programa:
**Cuenta** → pegar la llave → **Probar la llave** → **Guardar los cambios**.

Si se prefiere dejarlo sin IA, esa misma pantalla tiene la opción **Sin IA**,
que es además como viene de fábrica: así ningún dato sale de ese computador.

---

## Lo que esto no alcanza a revisar

El revisor prueba que el programa arranque y que las pantallas abran. **No
prueba el trabajo del día**: subir un ZIP de verdad, llenar un Formulario 210,
generar el Excel. Eso hay que hacerlo a mano una vez allá, con documentos de
prueba o suyos, nunca con los de un cliente real la primera vez.
