/* ==========================================================
   Pantalla de la cuenta.

   Dos cosas hace esta pantalla:
     1. Guardar el nombre de quien usa el programa (el sitio donde
        vivirá la cuenta el día que haya entrada con contraseña).
     2. Cambiar la llave de la IA sin tener que abrir el archivo .env
        con el bloc de notas.

   JavaScript plano, sin librerías, igual que el resto del programa.
   ========================================================== */

const avisoCuenta = document.getElementById("aviso-cuenta");
const avisoIA = document.getElementById("aviso-ia");

const campoNombre = document.getElementById("nombre");
const campoCorreo = document.getElementById("correo");
const campoLlave = document.getElementById("llave");
const campoModelo = document.getElementById("modelo");

const modoSinIA = document.getElementById("modo-sin-ia");
const modoConIA = document.getElementById("modo-con-ia");

const resultadoPrueba = document.getElementById("resultado-prueba");

/* Lo último que contestó el servidor. Sirve para saber si ya hay una
   llave guardada sin tener que volver a preguntar. */
let cuenta = null;


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

let temporizador = null;

function mostrarAviso(caja, texto, tipo) {
  caja.textContent = texto;
  caja.className = "aviso aviso-" + tipo;
  clearTimeout(temporizador);
  // Los mensajes de éxito se van solos; los de error se quedan hasta
  // que el contador haga algo al respecto.
  if (tipo === "exito") {
    temporizador = setTimeout(function () {
      caja.className = "aviso oculto";
    }, 5000);
  }
}

/* Saca el texto del error que mandó el servidor.

   FastAPI contesta de dos formas: cuando algo no pasó la revisión manda
   una lista de problemas, y cuando fue un error nuestro manda una frase.
   Aquí se atienden las dos para no mostrarle "[object Object]" a nadie. */
async function textoDeError(respuesta, porDefecto) {
  try {
    const datos = await respuesta.json();
    if (typeof datos.detail === "string") {
      return datos.detail;
    }
    if (Array.isArray(datos.detail) && datos.detail.length > 0) {
      return datos.detail[0].msg.replace("Value error, ", "");
    }
  } catch (error) {
    // El servidor no contestó JSON. Se usa el mensaje de siempre.
  }
  return porDefecto;
}


/* ----------------------------------------------------------
   Pintar lo que hay
   ---------------------------------------------------------- */

function pintar(datos) {
  cuenta = datos;

  document.getElementById("cuenta-titulo").textContent =
    datos.nombre || "Sin nombre todavía";
  document.getElementById("cuenta-clientes").textContent = datos.clientes;
  document.getElementById("cuenta-documentos").textContent = datos.documentos;

  campoNombre.value = datos.nombre || "";
  campoCorreo.value = datos.correo || "";
  campoModelo.value = datos.modelo_configurado || "";

  document.getElementById("ruta-datos").textContent = datos.carpeta_datos;
  document.getElementById("ruta-env").textContent = datos.archivo_env;

  // El estado de la IA, en una frase.
  const titulo = document.getElementById("estado-ia-titulo");
  const caja = document.getElementById("estado-ia");
  if (datos.ia_disponible) {
    titulo.textContent = "Rentai está encendida";
    caja.className = "estado-ia estado-ia-encendida";
  } else {
    titulo.textContent = "Rentai está apagada";
    caja.className = "estado-ia";
  }
  document.getElementById("estado-ia-motivo").textContent = datos.motivo;

  modoSinIA.checked = datos.sin_ia;
  modoConIA.checked = !datos.sin_ia;

  document.getElementById("llave-pista").textContent =
    datos.tiene_llave ? datos.pista_llave : "ninguna";
}

async function cargar() {
  try {
    const respuesta = await fetch("/api/cuenta");
    if (!respuesta.ok) {
      throw new Error("no se pudo");
    }
    pintar(await respuesta.json());
  } catch (error) {
    mostrarAviso(avisoCuenta,
      "No se pudo conectar con el servidor. ¿Sigue prendido?", "error");
  }
}


/* ----------------------------------------------------------
   Guardar el nombre
   ---------------------------------------------------------- */

document.getElementById("formulario-cuenta")
  .addEventListener("submit", async function (evento) {
    evento.preventDefault();

    try {
      const respuesta = await fetch("/api/cuenta", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nombre: campoNombre.value,
          correo: campoCorreo.value
        })
      });

      if (!respuesta.ok) {
        mostrarAviso(avisoCuenta,
          await textoDeError(respuesta, "No se pudo guardar."), "error");
        return;
      }

      pintar(await respuesta.json());
      mostrarAviso(avisoCuenta, "Guardado.", "exito");
    } catch (error) {
      mostrarAviso(avisoCuenta, "No se pudo conectar con el servidor.", "error");
    }
  });


/* ----------------------------------------------------------
   La llave
   ---------------------------------------------------------- */

/* Ver u ocultar lo que se está escribiendo. Empieza oculta porque
   normalmente uno pega la llave con alguien al lado. */
document.getElementById("boton-ver").addEventListener("click", function () {
  const oculta = campoLlave.type === "password";
  campoLlave.type = oculta ? "text" : "password";
  this.textContent = oculta ? "Ocultar" : "Ver";
});

function mostrarResultado(texto, sirve) {
  resultadoPrueba.textContent = texto;
  resultadoPrueba.className =
    "resultado-prueba " + (sirve ? "resultado-bien" : "resultado-mal");
}

/* Probar sin guardar: si el contador escribió una llave nueva se prueba
   esa, y si no, la que ya está guardada. */
document.getElementById("boton-probar")
  .addEventListener("click", async function () {
    const boton = this;
    boton.disabled = true;
    mostrarResultado("Preguntándole al servicio…", true);

    try {
      const respuesta = await fetch("/api/cuenta/ia/probar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ llave: campoLlave.value.trim() })
      });

      if (!respuesta.ok) {
        mostrarResultado(
          await textoDeError(respuesta, "No se pudo probar la llave."), false);
        return;
      }

      const datos = await respuesta.json();
      mostrarResultado(datos.motivo, datos.sirve);
    } catch (error) {
      mostrarResultado("No se pudo conectar con el servidor.", false);
    } finally {
      boton.disabled = false;
    }
  });

/* Guardar el modo, la llave y el modelo, todo de una. */
async function guardarIA(cambios) {
  const cuerpo = {
    sin_ia: modoSinIA.checked,
    modelo: campoModelo.value.trim()
  };

  // llave sin poner = "no la toque". Solo se manda cuando hay algo que
  // decir: una llave nueva, o el vacío que significa "bórrela".
  if (cambios && Object.prototype.hasOwnProperty.call(cambios, "llave")) {
    cuerpo.llave = cambios.llave;
  }
  if (cambios && Object.prototype.hasOwnProperty.call(cambios, "sin_ia")) {
    cuerpo.sin_ia = cambios.sin_ia;
  }

  try {
    const respuesta = await fetch("/api/cuenta/ia", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo)
    });

    if (!respuesta.ok) {
      mostrarAviso(avisoIA,
        await textoDeError(respuesta, "No se pudo guardar."), "error");
      return false;
    }

    pintar(await respuesta.json());
    campoLlave.value = "";
    campoLlave.type = "password";
    document.getElementById("boton-ver").textContent = "Ver";
    return true;
  } catch (error) {
    mostrarAviso(avisoIA, "No se pudo conectar con el servidor.", "error");
    return false;
  }
}

document.getElementById("boton-guardar-ia")
  .addEventListener("click", async function () {
    const escrita = campoLlave.value.trim();

    // Encender la IA sin llave no sirve de nada: se avisa antes de
    // escribir el archivo, para no dejarlo en un estado a medias.
    if (modoConIA.checked && !escrita && !(cuenta && cuenta.tiene_llave)) {
      mostrarAviso(avisoIA,
        "Para encender a Rentai hace falta una llave. Péguela arriba.",
        "error");
      return;
    }

    const cambios = escrita ? { llave: escrita } : {};
    if (await guardarIA(cambios)) {
      resultadoPrueba.className = "resultado-prueba oculto";
      mostrarAviso(avisoIA, "Listo. Los cambios ya están puestos.", "exito");
    }
  });

document.getElementById("boton-quitar")
  .addEventListener("click", async function () {
    if (!confirm("¿Borrar la llave guardada? Rentai queda apagada hasta que "
                 + "ponga otra.")) {
      return;
    }
    // Borrar la llave y apagar la IA van juntos: dejar el modo encendido
    // sin llave solo produce errores más adelante.
    if (await guardarIA({ llave: "", sin_ia: true })) {
      resultadoPrueba.className = "resultado-prueba oculto";
      mostrarAviso(avisoIA, "La llave se borró del archivo .env.", "exito");
    }
  });


cargar();
