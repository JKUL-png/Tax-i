/* ==========================================================
   Pantalla de la cuenta.

   Dos cosas hace esta pantalla:
     1. Guardar el nombre de quien usa el programa (el sitio donde
        vivirá la cuenta el día que haya entrada con contraseña).
     2. Elegir con cuál servicio de IA se habla, y probar la conexión,
        sin tener que abrir el archivo .env con el bloc de notas.

   JavaScript plano, sin librerías, igual que el resto del programa.
   ========================================================== */

const avisoCuenta = document.getElementById("aviso-cuenta");
const avisoIA = document.getElementById("aviso-ia");

const campoNombre = document.getElementById("nombre");
const campoCorreo = document.getElementById("correo");
const campoLlave = document.getElementById("llave");
const campoModelo = document.getElementById("modelo");

const selectorProveedor = document.getElementById("ia-proveedor");
const campoBaseUrl = document.getElementById("base-url");
const cajaBaseUrl = document.getElementById("campo-base-url");
const cajaLlave = document.getElementById("bloque-llave");
const cajaModelo = document.getElementById("campo-modelo");
const explicacion = document.getElementById("ia-explicacion");
const queSale = document.getElementById("ia-que-sale");
const ayudaModelo = document.getElementById("ayuda-modelo");

/* Cuál servicio concreto, dentro de los que hablan como OpenAI. */
const selectorServicio = document.getElementById("ia-servicio");
const cajaServicio = document.getElementById("campo-servicio");
const resumenServicio = document.getElementById("ia-servicio-resumen");
const cajaPrivacidad = document.getElementById("ia-privacidad");
const textoPrivacidad = document.getElementById("ia-privacidad-texto");
const enlacePrivacidad = document.getElementById("ia-privacidad-enlace");
const avisoCapaGratis = document.getElementById("ia-capa-gratis");

const resultadoPrueba = document.getElementById("resultado-prueba");

/* Lo último que contestó el servidor. Sirve para saber si ya hay una
   llave guardada sin tener que volver a preguntar. */
let cuenta = null;


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

/* El cómo está en comun.js. */
function mostrarAviso(caja, texto, tipo) { avisarEn(caja, texto, tipo); }

/* Saca el texto del error que mandó el servidor. Está en comun.js;
   aquí se deja el nombre viejo para no tocar los treinta sitios que lo
   llaman. */
async function textoDeError(respuesta, porDefecto) {
  return textoDelError(respuesta, porDefecto);
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
    titulo.textContent = "RentAI está encendida";
    caja.className = "estado-ia estado-ia-encendida";
  } else {
    titulo.textContent = "RentAI está apagada";
    caja.className = "estado-ia";
  }
  document.getElementById("estado-ia-motivo").textContent = datos.motivo;

  // El selector de servicio se arma con lo que dice el servidor, así
  // que agregar un proveedor nuevo no obliga a tocar esta pantalla.
  if (selectorProveedor.options.length === 0) {
    (datos.proveedores || []).forEach(function (uno) {
      const opcion = document.createElement("option");
      opcion.value = uno.clave;
      opcion.textContent = uno.nombre;
      selectorProveedor.appendChild(opcion);
    });
  }
  selectorProveedor.value = datos.proveedor;

  // Los servicios concretos que hablan como OpenAI. Van en el orden que
  // manda el servidor: primero los que tienen capa gratis.
  if (selectorServicio.options.length === 0) {
    (datos.servicios_compatibles || []).forEach(function (uno) {
      const opcion = document.createElement("option");
      opcion.value = uno.clave;
      opcion.textContent = uno.costo === "gratis"
        ? uno.nombre + " — tiene capa gratis"
        : (uno.costo === "pago" ? uno.nombre + " — de pago" : uno.nombre);
      selectorServicio.appendChild(opcion);
    });
  }
  selectorServicio.value = servicioSegunDireccion(datos.base_url);

  campoBaseUrl.value = datos.base_url || "";
  campoModelo.value = datos.modelo_configurado || "";

  document.getElementById("llave-pista").textContent =
    datos.tiene_llave ? datos.pista_llave : "ninguna";

  ajustarCampos();
}

/* Muestra u oculta la dirección y la llave según lo que pida el servicio
   elegido. Pedirle una llave a Ollama, que corre aquí mismo y no usa
   ninguna, solo confunde. */
function ajustarCampos() {
  const ficha = fichaDelProveedor(selectorProveedor.value);
  if (!ficha) return;

  // El selector de servicio concreto solo tiene sentido para los
  // compatibles con OpenAI: es donde hay que escoger a cuál se apunta.
  const esCompatible = ficha.clave === "openai_compatible";
  cajaServicio.classList.toggle("oculto", !esCompatible);
  if (esCompatible) {
    mostrarServicio();
  } else {
    cajaPrivacidad.classList.add("oculto");
  }

  // Por qué existe la fila de lectura: las capas gratis tienen tope
  // diario. Solo se dice cuando puede pasar de verdad.
  const puedeQuedarseSinCupo = ficha.costo === "mixto" || ficha.costo === "pago";
  avisoCapaGratis.classList.toggle("oculto", !puedeQuedarseSinCupo);
  if (puedeQuedarseSinCupo && cuenta) {
    avisoCapaGratis.textContent = cuenta.aviso_capa_gratis || "";
  }

  cajaBaseUrl.className = ficha.necesita_base_url ? "campo" : "campo oculto";
  cajaLlave.className = ficha.necesita_llave ? "bloque-llave" : "bloque-llave oculto";
  cajaModelo.className = ficha.clave === "ninguno" ? "campo oculto" : "campo";

  queSale.textContent = "Lo que sale de este computador: " + ficha.que_sale;
  queSale.className = ficha.clave === "ninguno" || ficha.clave === "ollama"
    ? "aviso-modo"
    : "aviso-modo aviso-modo-ia";

  if (ficha.clave === "ninguno") {
    explicacion.textContent =
      "El programa funciona completo. Usted clasifica los documentos a mano.";
  } else if (ficha.clave === "ollama") {
    explicacion.textContent =
      "Necesita Ollama instalado y corriendo en este computador. No pide llave.";
  } else if (ficha.clave === "openai_compatible") {
    explicacion.textContent =
      "Sirve para Groq, OpenAI, OpenRouter, Together, DeepSeek, LM Studio " +
      "y casi cualquier otro: todos hablan el mismo idioma. Escoja abajo " +
      "cuál y la dirección se llena sola.";
  } else {
    explicacion.textContent = "Los modelos Claude, de Anthropic. De pago.";
  }

  if (ficha.modelo_sugerido) {
    campoModelo.placeholder = ficha.modelo_sugerido;
    ayudaModelo.textContent =
      "El nombre exacto tal como lo llama su proveedor. Para este servicio, " +
      "por ejemplo: " + ficha.modelo_sugerido + ".";
  }

  // La dirección de fábrica se propone, no se impone: si el campo está
  // vacío se rellena, y si el contador escribió algo no se le toca.
  if (ficha.necesita_base_url && !campoBaseUrl.value && ficha.base_url_por_defecto) {
    campoBaseUrl.value = ficha.base_url_por_defecto;
  }
}

/* Qué servicio corresponde a una dirección ya guardada.

   Si el contador ya tenía puesta la dirección de Groq, al abrir la
   pantalla se muestra "Groq" en vez de "Otro": así ve dónde está parado
   en vez de tener que reconocer una URL. */
function servicioSegunDireccion(direccion) {
  const lista = (cuenta && cuenta.servicios_compatibles) || [];
  const limpia = (direccion || "").trim().replace(/\/$/, "");
  const encontrado = lista.find(function (uno) {
    return uno.base_url && uno.base_url.replace(/\/$/, "") === limpia;
  });
  return encontrado ? encontrado.clave : "otro";
}

function fichaDelServicio(clave) {
  const lista = (cuenta && cuenta.servicios_compatibles) || [];
  return lista.find(function (uno) { return uno.clave === clave; }) || null;
}

/* Muestra lo que hay que saber del servicio elegido: qué cuesta y qué
   hace con los documentos. Lo segundo importa más que lo primero: aquí
   va información tributaria de terceros que no dieron permiso. */
function mostrarServicio() {
  const ficha = fichaDelServicio(selectorServicio.value);
  if (!ficha) return;

  resumenServicio.textContent = ficha.resumen || "";

  if (ficha.privacidad) {
    textoPrivacidad.textContent = ficha.privacidad;
    cajaPrivacidad.classList.remove("oculto");
  } else {
    cajaPrivacidad.classList.add("oculto");
  }

  if (ficha.enlace) {
    enlacePrivacidad.href = ficha.enlace;
    enlacePrivacidad.textContent = ficha.enlace_texto || ficha.enlace;
    enlacePrivacidad.parentElement.classList.remove("oculto");
  } else {
    enlacePrivacidad.parentElement.classList.add("oculto");
  }
}

/* Al elegir un servicio se le pone su dirección. Es lo único que cambia:
   la llave la escribe el contador. */
selectorServicio.addEventListener("change", function () {
  const ficha = fichaDelServicio(selectorServicio.value);
  if (ficha && ficha.base_url) campoBaseUrl.value = ficha.base_url;
  if (ficha && ficha.clave === "otro") campoBaseUrl.value = "";
  mostrarServicio();
});

function fichaDelProveedor(clave) {
  if (!cuenta || !cuenta.proveedores) return null;
  return cuenta.proveedores.find(function (uno) { return uno.clave === clave; });
}

selectorProveedor.addEventListener("change", function () {
  const ficha = fichaDelProveedor(selectorProveedor.value);
  // Al cambiar de servicio, la dirección y el modelo del anterior ya no
  // valen: se ponen los del nuevo en vez de dejar los viejos, que
  // fallarían con un error confuso.
  if (ficha) {
    campoBaseUrl.value = ficha.base_url_por_defecto || "";
    campoModelo.value = ficha.modelo_sugerido || "";
  }
  ajustarCampos();
});

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
        // Se prueba lo que está ESCRITO en la pantalla, no lo guardado:
        // así el contador comprueba antes de cambiar nada.
        body: JSON.stringify({
          proveedor: selectorProveedor.value,
          base_url: campoBaseUrl.value.trim(),
          llave: campoLlave.value.trim()
        })
      });

      if (!respuesta.ok) {
        mostrarResultado(
          await textoDeError(respuesta, "No se pudo probar la conexión."), false);
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
    proveedor: (cambios && cambios.proveedor) || selectorProveedor.value,
    base_url: campoBaseUrl.value.trim(),
    modelo: campoModelo.value.trim()
  };

  // llave sin poner = "no la toque". Solo se manda cuando hay algo que
  // decir: una llave nueva, o el vacío que significa "bórrela".
  if (cambios && Object.prototype.hasOwnProperty.call(cambios, "llave")) {
    cuerpo.llave = cambios.llave;
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
    const ficha = fichaDelProveedor(selectorProveedor.value);

    // Elegir un servicio que pide llave sin ponerla no sirve de nada: se
    // avisa antes de escribir el archivo, para no dejarlo a medias.
    if (ficha && ficha.necesita_llave && !escrita &&
        !(cuenta && cuenta.tiene_llave)) {
      mostrarAviso(avisoIA,
        "\"" + ficha.nombre + "\" necesita una llave. Péguela arriba.",
        "error");
      return;
    }

    if (ficha && ficha.necesita_base_url && !campoBaseUrl.value.trim()) {
      mostrarAviso(avisoIA,
        "\"" + ficha.nombre + "\" necesita la dirección del servicio.",
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
    if (!confirm("¿Borrar la llave guardada? RentAI queda apagada hasta que "
                 + "ponga otra.")) {
      return;
    }
    // Borrar la llave y apagar la IA van juntos: dejar un servicio
    // elegido sin su llave solo produce errores más adelante.
    if (await guardarIA({ llave: "", proveedor: "ninguno" })) {
      resultadoPrueba.className = "resultado-prueba oculto";
      mostrarAviso(avisoIA, "La llave se borró del archivo .env.", "exito");
    }
  });


cargar();


/* ==========================================================
   La revisión de arranque y el modo demostración
   ========================================================== */

const revisionResumen = document.getElementById("revision-resumen");
const revisionLista = document.getElementById("revision-lista");
const botonRevisar = document.getElementById("boton-revisar");

const demoInterruptor = document.getElementById("demo-interruptor");
const demoMarca = document.getElementById("demo-marca");
const avisoDemo = document.getElementById("aviso-demo");

/* Cómo se pinta cada nivel de la revisión. */
const COLORES_DE_REVISION = {
  bien: "etiqueta-exito",
  aviso: "etiqueta-alerta",
  problema: "etiqueta-error"
};
const PALABRAS_DE_REVISION = {
  bien: "Listo",
  aviso: "Ojo",
  problema: "Hay que arreglarlo"
};

async function cargarRevision(probarIA) {
  revisionResumen.textContent = probarIA
    ? "Revisando, y probando el servicio de IA…"
    : "Revisando…";
  revisionLista.textContent = "";

  try {
    const respuesta = await fetch(
      "/api/revision" + (probarIA ? "?probar_ia=si" : "")
    );
    if (!respuesta.ok) throw new Error();
    dibujarRevision(await respuesta.json());
  } catch (e) {
    revisionResumen.textContent = "No se pudo hacer la revisión.";
  }
}

function dibujarRevision(informe) {
  revisionResumen.textContent = informe.resumen;
  revisionLista.textContent = "";

  informe.puntos.forEach(function (punto) {
    const fila = document.createElement("div");
    fila.className = "tarjeta revision-punto";

    const titulo = document.createElement("p");
    titulo.className = "revision-titulo";

    const marca = document.createElement("span");
    marca.className = "etiqueta " + (COLORES_DE_REVISION[punto.nivel] || "");
    marca.textContent = PALABRAS_DE_REVISION[punto.nivel] || punto.nivel;
    titulo.appendChild(marca);
    titulo.appendChild(document.createTextNode(" " + punto.titulo));
    fila.appendChild(titulo);

    const mensaje = document.createElement("p");
    mensaje.className = "ayuda";
    mensaje.textContent = punto.mensaje;
    fila.appendChild(mensaje);

    // Qué hacer. Solo aparece cuando hay algo que hacer: repetir
    // "todo bien" con instrucciones sería ruido.
    if (punto.que_hacer) {
      const hacer = document.createElement("p");
      hacer.className = "ayuda revision-que-hacer";
      hacer.textContent = punto.que_hacer;
      fila.appendChild(hacer);
    }

    revisionLista.appendChild(fila);
  });
}

if (botonRevisar) {
  botonRevisar.addEventListener("click", function () {
    botonRevisar.disabled = true;
    cargarRevision(true).finally(function () {
      botonRevisar.disabled = false;
    });
  });
}

/* ----------------------------------------------------------
   Modo demostración
   ---------------------------------------------------------- */

async function cargarDemostracion() {
  try {
    const respuesta = await fetch("/api/demostracion");
    if (!respuesta.ok) return;
    mostrarDemostracion(await respuesta.json());
  } catch (e) {
    // Si no se puede preguntar, el resto de la pantalla funciona igual.
  }
}

function mostrarDemostracion(estado) {
  if (demoInterruptor) demoInterruptor.checked = !!estado.activo;
  if (demoMarca && estado.marca) demoMarca.textContent = estado.marca;
}

if (demoInterruptor) {
  demoInterruptor.addEventListener("change", async function () {
    const prendiendo = demoInterruptor.checked;

    // Apagarlo BORRA los clientes inventados. Se pregunta antes: es un
    // borrado, y en este programa ningún borrado pasa sin confirmar.
    if (!prendiendo) {
      const seguro = confirm(
        "Se van a borrar los clientes de ejemplo y sus documentos"
        + " inventados.\n\nSus clientes de verdad NO se tocan.\n\n"
        + "¿Apagar el modo demostración?"
      );
      if (!seguro) {
        demoInterruptor.checked = true;
        return;
      }
    }

    demoInterruptor.disabled = true;
    try {
      const respuesta = await fetch("/api/demostracion", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prendido: prendiendo })
      });
      if (!respuesta.ok) throw new Error(await textoDelError(respuesta));
      const estado = await respuesta.json();
      mostrarDemostracion(estado);

      avisarEn(avisoDemo, prendiendo
        ? "Cliente de ejemplo cargado. Aparece en la lista de la"
          + " izquierda, marcado como ficticio."
        : "Modo demostración apagado. Se quitaron "
          + contar(estado.quitados || 0, "cliente inventado",
                   "clientes inventados") + ".",
        "exito");

      // La lista de la izquierda y la revisión cambiaron.
      cargarRevision(false);
      if (window.RielTaxi && window.RielTaxi.recargar) {
        window.RielTaxi.recargar();
      }
    } catch (e) {
      demoInterruptor.checked = !prendiendo;
      avisarEn(avisoDemo, e.message || "No se pudo cambiar el modo.",
               "error");
    } finally {
      demoInterruptor.disabled = false;
    }
  });
}

cargarRevision(false);
cargarDemostracion();
