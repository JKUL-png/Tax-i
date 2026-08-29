# Cómo probar Tax-i en un computador con Windows

Guía paso a paso. No hay que saber programar ni entender nada de lo que dice
la pantalla negra. Son nueve partes y en total toma unos 20 minutos, casi
todos de espera.

**Lo que vamos a hacer, en una frase:** armar un paquete aquí en el Mac,
pasarlo al Windows en una memoria USB, instalar Python allá, y hacer doble
clic en dos archivos.

---

## Antes de empezar

Necesita tres cosas:

1. Este mismo Mac, con el proyecto.
2. Una **memoria USB** (cualquiera, el paquete pesa menos de 1 MB).
3. El **computador con Windows**, y poder instalar programas en él.

> **Una advertencia que sí importa.** No ponga el programa en el Escritorio ni
> en Documentos si ese computador tiene **OneDrive**. OneDrive sube a la nube
> todo lo que hay en esas carpetas, y aquí se van a guardar documentos
> tributarios de clientes. En la Parte 4 lo vamos a poner en `C:\tax-i`, que
> está fuera de OneDrive.

---

# PARTE 1 — En el Mac: armar el paquete

### Paso 1.1

Abra la carpeta del proyecto en el Finder (`asistente-renta`).

### Paso 1.2

Haga **doble clic en `empacar.sh`**.

Se abre una ventana negra (la Terminal) y en dos segundos dice algo así:

```
  Listo.

  El paquete quedó en el Escritorio:  tax-i.zip
  Trae 42 archivos, y ninguno es de sus clientes.
```

### Paso 1.3

Cierre esa ventana. En el **Escritorio** del Mac hay ahora un archivo
**`tax-i.zip`**. Ese es todo el programa.

> **¿Por qué no copiar la carpeta entera y ya?** Porque adentro hay dos cosas
> que **no** deben viajar. `.venv/` son programas compilados para Mac, con
> rutas del Mac escritas adentro: en Windows no sirven, y además le estorban
> al entorno bueno que se va a crear allá. Y `datos/` son los documentos de
> clientes de verdad, que no tienen por qué andar en dos computadores.
> `empacar.sh` deja las dos afuera solo.

### Paso 1.4

Copie `tax-i.zip` a la memoria USB.

---

# PARTE 2 — Pasar el paquete al Windows

Conecte la memoria USB al computador con Windows y **copie `tax-i.zip` al
disco C:**

Para llegar a C: abra el **Explorador de archivos** (el ícono de la carpeta
amarilla, en la barra de abajo) y en la columna izquierda haga clic en
**"Este equipo"** y después en **"Disco local (C:)"**. Arrastre el
`tax-i.zip` ahí.

Si Windows dice que no tiene permiso para escribir en C:, no pelee con eso:
déjelo en el Escritorio por ahora y en la Parte 4 le decimos dónde ponerlo.

---

# PARTE 3 — Instalar Python en el Windows

Python es el motor que hace funcionar el programa. Es gratis y lo hace la
misma gente que hace el lenguaje. Se instala una sola vez.

### Paso 3.1

Abra el navegador y vaya a:

```
https://www.python.org/downloads/
```

### Paso 3.2

Haga clic en el botón grande amarillo que dice **"Download Python 3.13.x"**
(el número final puede ser otro, no importa). Se descarga un archivo.

> **No lo instale desde la Microsoft Store**, aunque Windows se lo ofrezca.
> Esa versión a veces no trae la pieza que necesita nuestro lanzador.

### Paso 3.3

Abra el archivo que se descargó. Aparece una ventana de instalación.

### 🔴 Paso 3.4 — El paso donde todo el mundo se equivoca

**Antes de darle a "Install Now"**, abajo de esa ventana hay una casilla
pequeña que dice:

> ☐ **Add python.exe to PATH**
>
> (en versiones más viejas dice *"Add Python 3.x to PATH"*)

**Marque esa casilla.** Es un cuadrito chiquito y está fácil de pasar por
alto, pero si no lo marca, el programa no arranca y el error que sale no
dice que fue por esto.

### Paso 3.5

Ahora sí, **"Install Now"**. Se demora un par de minutos. Cuando diga
*"Setup was successful"*, cierre la ventana.

> ¿Se le olvidó marcar la casilla? No pasa nada: vuelva a abrir el mismo
> archivo descargado, elija **"Modify"**, dele **"Next"** hasta la pantalla
> que dice *Advanced Options*, y ahí marque
> **"Add Python to environment variables"**. Después **"Install"**.

---

# PARTE 4 — Descomprimir el programa

### Paso 4.1

Vaya a donde dejó `tax-i.zip` (el disco C:, o el Escritorio).

### Paso 4.2

Haga **clic derecho** sobre `tax-i.zip` → **"Extraer todo…"**.

### Paso 4.3

Se abre una ventana que pregunta dónde extraerlo. Borre lo que diga ahí y
escriba exactamente:

```
C:\tax-i
```

Después haga clic en **"Extraer"**.

### Paso 4.4 — Compruebe que quedó bien

Abra la carpeta `C:\tax-i`. **Adentro tiene que verse `iniciar.bat`
directamente**, junto con las carpetas `app`, `static` y `pruebas`.

Si en vez de eso ve *una sola carpeta* adentro (por ejemplo otra llamada
`tax-i`), entre a esa carpeta, seleccione todo lo que hay adentro
(Control + A, o arrastrando con el mouse), córtelo (Control + X) y péguelo
un nivel arriba (Control + V).

> **Nunca haga doble clic en `iniciar.bat` desde adentro del ZIP.** Windows
> deja mirar adentro de un ZIP como si fuera una carpeta normal, y es una
> trampa: el programa arranca desde una carpeta temporal, se comporta raro y
> después desaparece. Primero extraer, siempre.

---

# PARTE 5 — Prender el programa por primera vez

### Paso 5.1

En `C:\tax-i`, haga **doble clic en `iniciar.bat`**.

### Paso 5.2 — Si sale una pantalla azul de advertencia

Puede aparecer una ventana azul que dice *"Windows protegió su PC"*. Es
normal: Windows desconfía de todo archivo que llegó de afuera y no está
firmado por una empresa grande.

- Haga clic en **"Más información"**
- Después en **"Ejecutar de todas formas"**

### Paso 5.3 — Espere

Se abre una ventana negra que dice:

```
Primera vez: preparando el entorno (esto puede tardar un minuto)...
```

**Esto se demora entre uno y tres minutos.** Está bajando de internet las
piezas que el programa necesita. Se ven pasar muchas líneas de texto: es
normal, no hay que leerlas. Déjelo quieto.

### Paso 5.4 — Cuando termine

La ventana negra queda mostrando esto:

```
  Tax-i corriendo en:                http://localhost:8000
  Para apagarlo: Control + C
```

**Eso significa que funcionó.**

> ⚠️ **No cierre esa ventana negra.** Es el programa. Mientras esté abierta,
> Tax-i está prendido; si la cierra, se apaga.

### Paso 5.5 — Si aparece una alerta del firewall

Si Windows pregunta si permite el acceso a la red, puede darle **Cancelar**
tranquilamente. El programa solo habla consigo mismo dentro del computador y
no necesita ese permiso.

---

# PARTE 6 — Abrir el programa

Deje esa ventana negra abierta, abra el navegador (Edge o Chrome) y en la
barra de direcciones escriba:

```
localhost:8000
```

Dele Enter. **Tiene que aparecer la pantalla de Tax-i**, con el título arriba
a la izquierda y "Agregar cliente" debajo.

Si aparece: felicitaciones, el programa ya corre en Windows. Falta comprobar
que corra *bien*, que es la parte siguiente.

---

# PARTE 7 — La revisión automática

Esto revisa, una por una, las cosas que funcionan en el Mac y se rompen en
Windows. Es la parte importante de toda la guía.

### Paso 7.1 — Apague el programa

Vuelva a la ventana negra y presione **Control + C**.

Si pregunta *"¿Desea terminar el trabajo por lotes (S/N)?"*, escriba **S** y
dele Enter. La ventana se cierra.

### Paso 7.2 — Corra la revisión

En `C:\tax-i`, haga **doble clic en `revisar.bat`**.

### Paso 7.3 — Espere medio minuto y lea el final

Van saliendo líneas que empiezan con `OK` o con `FALLA`. Al final aparece el
resultado:

```
==============================================================
 28 de 28 revisiones pasaron.
 Todo bien. El programa funciona en este computador.
==============================================================
```

El número puede ser 27, 28 o 29 según el computador — algunas revisiones
solo aplican en ciertos casos. **Lo que importa es que los dos números sean
iguales** y que diga "Todo bien".

**Si dice "Todo bien": terminó.** El programa funciona en ese computador.

**Si dice "HAY FALLAS":** no toque nada. Busque hacia arriba las líneas que
dicen `FALLA` — cada una explica qué pasó. Tome una foto de la pantalla o
cópiela completa y mándemela; con eso alcanza para arreglarlo.

> **La revisión no toca nada suyo.** No borra ni cambia ningún documento ni
> ningún cliente. Los archivos de prueba que crea los borra al terminar.

---

# PARTE 8 — Probar el trabajo de verdad

La revisión automática comprueba que el programa *arranque* y que las
pantallas *abran*. No comprueba el trabajo del día. Eso hay que hacerlo a
mano, una vez, con **documentos de prueba o suyos — nunca de un cliente real
la primera vez**.

Prenda otra vez el programa (doble clic en `iniciar.bat`), abra
`localhost:8000` y haga este recorrido:

1. **Cree un cliente** de mentiras: nombre "Prueba Uno", dígitos 07, una
   fecha cualquiera.
2. **Entre a ese cliente** (clic en el nombre).
3. **Suba unos documentos**: arrastre dos o tres PDF a la zona de subir.
   Pruebe también arrastrando un ZIP.
4. **Pruebe un nombre difícil.** Este es el error clásico de Windows: cambie
   el nombre de un PDF a `Certificado 2025 Bancolombia año.pdf` y súbalo.
   Tiene que quedar guardado y con la ñ y la tilde bien puestas.
5. **Marque algo del checklist** y compruebe que se queda marcado al recargar.
6. **Abra el Formulario 210**, escriba un valor y genere el archivo de Excel.
7. **Borre el cliente de prueba** cuando termine.

Si algo de esto falla, anote **en qué paso** y qué decía la pantalla.

---

# PARTE 9 — Poner la llave de la IA (opcional)

Si quiere que Rentai funcione allá:

1. En el programa, arriba a la derecha, haga clic en **"Cuenta"**.
2. Pegue la llave en el campo **"Llave nueva"**.
3. Haga clic en **"Probar la llave"**. Tiene que decir *"La llave sirve"*.
4. Marque **"Con Rentai encendida"** y haga clic en **"Guardar los cambios"**.

Si prefiere dejarlo sin IA, no haga nada: viene apagada de fábrica, y así
ningún dato de ningún cliente sale de ese computador.

---

# Para el día a día

| Quiero… | Hago… |
|---|---|
| Prender el programa | Doble clic en `iniciar.bat` |
| Usarlo | `localhost:8000` en el navegador |
| Apagarlo | Control + C en la ventana negra (y **S** si pregunta) |
| Volver a revisar que todo esté bien | Doble clic en `revisar.bat` |

La segunda vez y las siguientes, `iniciar.bat` arranca en dos segundos: solo
la primera vez se demora.

---

# Si algo sale mal

| Lo que pasa | Qué es | Qué hacer |
|---|---|---|
| La ventana negra se abre y se cierra de una | Falta Python, o no se marcó la casilla del PATH | Repita la Parte 3, con cuidado en el Paso 3.4 |
| Dice `No se encontro Python` | Lo mismo de arriba | Repita la Parte 3 |
| Dice `Hubo un problema instalando las dependencias` | No hay internet, o lo bloqueó el antivirus | Revise la conexión y vuelva a darle doble clic |
| El navegador dice "No se puede acceder a este sitio" | El programa no está prendido | Doble clic en `iniciar.bat` y espere a que diga "corriendo en" |
| `revisar.bat` dice "Todavia no esta preparado el entorno" | Nunca se ha corrido `iniciar.bat` | Haga la Parte 5 primero |
| Errores raros al guardar documentos | La carpeta quedó muy adentro y Windows corta las rutas a 260 caracteres | Mueva todo a `C:\tax-i` |
| Un error largo que termina en `An Application Control policy has blocked this file` | Windows bloqueó una pieza del programa | Lea la sección siguiente, **Windows bloqueó un archivo** |
| Cualquier otra cosa | — | Foto de la pantalla completa y me la manda |

---

# Windows bloqueó un archivo

### Cómo se ve

`iniciar.bat` alcanza a decir *"Tax-i corriendo en..."* y después suelta una
pared de texto rojo que termina así:

```
ImportError: DLL load failed while importing _pydantic_core:
An Application Control policy has blocked this file.
```

### Qué está pasando

**No es un error del programa.** El programa está bien instalado. Lo que pasa
es que **Windows 11 se negó a abrir uno de sus archivos.**

El culpable es el **Control inteligente de aplicaciones** (*Smart App
Control*), una función de seguridad que traen algunos Windows 11 nuevos.
Funciona así: solo deja correr archivos que vengan **firmados** por una
empresa que Microsoft ya conoce, o que mucha gente en el mundo haya usado
antes. Todo lo demás lo bloquea, sin preguntar.

Varias librerías de Python traen adentro archivos compilados sin firmar
—`_pydantic_core` es uno—, y para el Control inteligente eso es sospechoso
aunque venga del repositorio oficial de Python.

> **Reinstalar no sirve para nada.** El archivo ya está ahí. Volver a
> instalarlo, borrar la carpeta `.venv` o reinstalar Python deja todo
> exactamente igual, porque no falta nada: está bloqueado.

### La única solución: apagar el Control inteligente de aplicaciones

Microsoft lo dice de frente: **no hay forma de permitir un solo programa.**
Es todo o nada. O se apaga la función, o el programa no corre en ese
computador.

**Antes de hacerlo, lea esto:**

Al apagarlo, Windows le va a mostrar un aviso diciendo que **no se puede
volver a activar sin reinstalar Windows desde cero**. Microsoft dice que
las actualizaciones recientes ya permiten volver a activarlo sin reinstalar,
pero el aviso sigue apareciendo. **Dé por hecho que es un camino de una sola
vía** y decida con esa idea: en el computador de pruebas, sin problema; en el
computador de trabajo de alguien más, pregúntele primero.

### Paso a paso

**Paso 1.** Haga clic en el botón de Inicio y escriba:

```
Seguridad de Windows
```

Dele Enter para abrirla.

**Paso 2.** En la columna de la izquierda, haga clic en **"Control de
aplicaciones y navegador"** (el ícono es una ventanita con un candado).

**Paso 3.** Busque la sección **"Control inteligente de aplicaciones"** y
haga clic en **"Configuración de Control inteligente de aplicaciones"**.

> **¿No aparece esa sección?** Entonces no es esto. Puede ser una política
> puesta por una empresa o un colegio en ese computador. Mándeme una foto de
> esa pantalla.

**Paso 4.** Va a ver tres opciones: *Activado*, *Evaluación* y *Desactivado*.
Marque **"Desactivado"**.

**Paso 5.** Windows pregunta si está seguro y advierte lo de reinstalar.
Confirme.

**Paso 6.** **Reinicie el computador.** Sin reiniciar, a veces sigue
bloqueando.

**Paso 7.** Vuelva a `C:\tax-i` y haga doble clic en `iniciar.bat`. Ahora
sí tiene que llegar hasta *"Tax-i corriendo en..."* y quedarse ahí, sin
texto rojo.

### Si prefiere no apagarlo

Es una decisión razonable. En ese caso, ese computador no puede correr Tax-i,
y toca probarlo en otro Windows. No hay término medio: Microsoft no da forma
de hacer una excepción para un solo programa.

---

# Y si toca empezar de nuevo

Borrar `C:\tax-i` y volver a la Parte 4. No se pierde nada del Mac: el
original sigue intacto allá. Lo único que se perdería son los clientes y
documentos que haya creado *en el Windows* durante la prueba, que son de
mentiras.
