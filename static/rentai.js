/* ==========================================================
   RentAI: la asistente.

   Cerrada es un botón cuadrado en la esquina de abajo a la derecha, con
   el logo y nada más. El mismo botón abre y cierra la conversación, que
   trae el historial de lo que se ha hablado sobre este cliente.

   RentAI propone; nunca anota sola. Cada propuesta sale con el documento
   de donde salió y con dos botones: anotar o descartar.

   JavaScript plano, sin librerías.
   ========================================================== */

(function () {

const idCliente = new URLSearchParams(window.location.search).get("id");
if (!idCliente) return;

const caja = document.getElementById("rentai");
const botonAbrir = document.getElementById("rentai-abrir");
const aviso = document.getElementById("rentai-aviso");
const estado = document.getElementById("rentai-estado");
const mensajes = document.getElementById("rentai-mensajes");
const campoTexto = document.getElementById("rentai-texto");
const botonEnviar = document.getElementById("rentai-enviar");
const botonMinimizar = document.getElementById("rentai-minimizar");
const botonLimpiar = document.getElementById("rentai-limpiar");

let disponible = false;
let hablando = false;


/* ----------------------------------------------------------
   El punto de aviso

   Un punto pequeño encima del botón cuando hay algo esperándolo: una
   propuesta que RentAI hizo y que él todavía no anotó ni descartó. Sin
   texto y sin globo — el contador está trabajando en otra cosa, y un
   cartel que se le atraviesa es peor que no avisar.

   Se cuenta de las tarjetas que ya están pintadas, así que no hace
   falta preguntarle nada más al servidor.
   ---------------------------------------------------------- */

function revisarAviso() {
  const esperando = mensajes.querySelectorAll(
    ".propuesta:not(.propuesta-anotada):not(.propuesta-descartada)").length;
  const abierta = !caja.classList.contains("rentai-cerrada");
  aviso.classList.toggle("oculto", abierta || esperando === 0);
}


/* ----------------------------------------------------------
   Abrir y cerrar
   ---------------------------------------------------------- */

function abrir() {
  caja.classList.remove("rentai-cerrada");
  botonAbrir.setAttribute("aria-expanded", "true");
  botonAbrir.setAttribute("aria-label", "Cerrar RentAI");
  campoTexto.focus();
  alFinal();
  revisarAviso();
  guardarSiEstabaAbierta(true);
}

function cerrar() {
  caja.classList.add("rentai-cerrada");
  botonAbrir.setAttribute("aria-expanded", "false");
  botonAbrir.setAttribute("aria-label", "Abrir RentAI");
  revisarAviso();
  guardarSiEstabaAbierta(false);
}

/* El mismo botón abre y cierra. */
function alternar() {
  if (caja.classList.contains("rentai-cerrada")) abrir(); else cerrar();
}

/* Se recuerda si la dejó abierta, igual que las secciones de la página.
   Solo se guarda eso: ningún dato de ningún cliente. */
function guardarSiEstabaAbierta(abierta) {
  try {
    window.localStorage.setItem("rentai-abierta", abierta ? "si" : "no");
  } catch (error) { /* hay navegadores que no dejan guardar */ }
}

function estabaAbierta() {
  try {
    return window.localStorage.getItem("rentai-abierta") === "si";
  } catch (error) {
    return false;
  }
}


/* ----------------------------------------------------------
   Pedirle cosas al servidor
   ---------------------------------------------------------- */

async function pedir(direccion, opciones) {
  const respuesta = await fetch(direccion, opciones);
  if (!respuesta.ok) {
    // textoDelError vive en comun.js. El texto de reserva lleva el
    // número del error, que es lo único útil cuando el servidor no
    // alcanzó ni a contestar en JSON.
    throw new Error(await textoDelError(
      respuesta,
      "No se pudo completar la operación (" + respuesta.status + ")."
    ));
  }
  if (respuesta.status === 204) return null;
  return respuesta.json();
}


/* ----------------------------------------------------------
   Dibujar la conversación
   ---------------------------------------------------------- */

function enPesos(numero) {
  return "$ " + Number(numero).toLocaleString("es-CO",
                                              { maximumFractionDigits: 2 });
}

function alFinal() {
  mensajes.scrollTop = mensajes.scrollHeight;
}

function dibujarMensaje(mensaje) {
  const globo = document.createElement("div");
  globo.className = "rentai-mensaje rentai-" + mensaje.papel;

  const texto = document.createElement("p");
  texto.className = "rentai-texto";
  texto.textContent = mensaje.texto;
  globo.appendChild(texto);

  (mensaje.propuestas || []).forEach(function (propuesta) {
    globo.appendChild(dibujarPropuesta(propuesta));
  });

  mensajes.appendChild(globo);
  return globo;
}

function dibujarPropuesta(propuesta) {
  const tarjeta = document.createElement("div");
  tarjeta.className = "propuesta";

  /* Si esta misma cifra ya está anotada en esa casilla, la propuesta se
     muestra como cumplida en vez de ofrecer anotarla otra vez. */
  const cumplida = yaAnotado[propuesta.celda] === propuesta.valor;

  /* Obligación del proyecto: todo lo que salga de una IA se muestra
     marcado, y con de dónde salió. */
  const marca = document.createElement("span");
  marca.className = "etiqueta etiqueta-ia";
  marca.textContent = "Lectura automática · verificar";
  tarjeta.appendChild(marca);

  if (propuesta.contexto) {
    const rastro = document.createElement("p");
    rastro.className = "propuesta-rastro";
    rastro.textContent = propuesta.contexto;
    tarjeta.appendChild(rastro);
  }

  const titulo = document.createElement("p");
  titulo.className = "propuesta-titulo";
  titulo.textContent = propuesta.descripcion || propuesta.celda;
  /* Hay conceptos de la plantilla que son un párrafo entero con artículos
     y decretos. En la tarjeta se muestran tres renglones y el resto sale
     al pasar el mouse. */
  titulo.title = propuesta.descripcion || propuesta.celda;
  tarjeta.appendChild(titulo);

  const cifra = document.createElement("p");
  cifra.className = "propuesta-cifra";
  cifra.textContent = enPesos(propuesta.valor);
  tarjeta.appendChild(cifra);

  const detalle = document.createElement("p");
  detalle.className = "propuesta-detalle";
  const partes = [propuesta.celda];
  if (propuesta.renglon) partes.push("renglón " + propuesta.renglon);
  if (propuesta.documento) partes.push(propuesta.documento);
  detalle.textContent = partes.join(" · ");
  tarjeta.appendChild(detalle);

  if (propuesta.por_que) {
    const porque = document.createElement("p");
    porque.className = "propuesta-porque";
    porque.textContent = propuesta.por_que;
    tarjeta.appendChild(porque);
  }

  if (cumplida) {
    tarjeta.classList.add("propuesta-anotada");
    const listo = document.createElement("p");
    listo.className = "propuesta-lista";
    listo.textContent = "Ya está anotado en " + propuesta.celda + ".";
    tarjeta.appendChild(listo);
    return tarjeta;
  }

  const botones = document.createElement("div");
  botones.className = "propuesta-botones";

  const anotar = document.createElement("button");
  anotar.type = "button";
  anotar.className = "boton";
  anotar.textContent = "Anotar";
  anotar.addEventListener("click", async function () {
    anotar.disabled = true;
    try {
      await pedir("/api/clientes/" + idCliente + "/chat/anotar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          celda: propuesta.celda,
          valor: propuesta.valor,
          documento: propuesta.documento
        })
      });
      tarjeta.classList.add("propuesta-anotada");
      yaAnotado[propuesta.celda] = propuesta.valor;
      botones.textContent = "";
      const listo = document.createElement("p");
      listo.className = "propuesta-lista";
      listo.textContent = "Anotado en " + propuesta.celda + ".";
      tarjeta.appendChild(listo);
      /* La sección del formulario se entera y se refresca sola. */
      document.dispatchEvent(new CustomEvent("valor-anotado"));
      revisarAviso();
    } catch (error) {
      anotar.disabled = false;
      mostrarError(error.message);
    }
  });

  const descartar = document.createElement("button");
  descartar.type = "button";
  descartar.className = "boton-texto";
  descartar.textContent = "Descartar";
  descartar.addEventListener("click", function () {
    tarjeta.classList.add("propuesta-descartada");
    botones.textContent = "";
    revisarAviso();
  });

  botones.appendChild(anotar);
  botones.appendChild(descartar);
  tarjeta.appendChild(botones);

  return tarjeta;
}

function mostrarError(texto) {
  const globo = document.createElement("div");
  globo.className = "rentai-mensaje rentai-problema";
  globo.textContent = texto;
  mensajes.appendChild(globo);
  alFinal();
}

function mostrarVacio() {
  const globo = document.createElement("div");
  globo.className = "rentai-vacio";
  globo.textContent = disponible
    ? "Pregúntele lo que quiera sobre este cliente: qué dice un documento,"
      + " qué falta, o dictele una cifra para que la anote."
    : "RentAI está apagada. Todo lo demás del programa funciona igual.";
  mensajes.appendChild(globo);
}


/* ----------------------------------------------------------
   Hablar
   ---------------------------------------------------------- */

async function enviar() {
  const texto = campoTexto.value.trim();
  if (!texto || hablando) return;

  if (!disponible) {
    mostrarError(estado.textContent
      || "RentAI está apagada en la configuración.");
    return;
  }

  hablando = true;
  botonEnviar.disabled = true;
  campoTexto.value = "";
  ajustarAlto();

  dibujarMensaje({ papel: "contador", texto: texto, propuestas: [] });

  const pensando = document.createElement("div");
  pensando.className = "rentai-mensaje rentai-rentai rentai-pensando";
  pensando.textContent = "Leyendo los documentos…";
  mensajes.appendChild(pensando);
  alFinal();

  try {
    const respuesta = await pedir("/api/clientes/" + idCliente + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto })
    });
    pensando.remove();
    dibujarMensaje({
      papel: "rentai",
      texto: respuesta.respuesta,
      propuestas: respuesta.propuestas
    });
    if (respuesta.descartadas > 0) {
      const nota = document.createElement("p");
      nota.className = "rentai-nota";
      nota.textContent = respuesta.descartadas === 1
        ? "Se descartó 1 propuesta que apuntaba a una casilla que no existe"
          + " o que tiene fórmula."
        : "Se descartaron " + respuesta.descartadas + " propuestas que"
          + " apuntaban a casillas que no existen o que tienen fórmula.";
      mensajes.appendChild(nota);
    }
  } catch (error) {
    pensando.remove();
    mostrarError(error.message);
  } finally {
    hablando = false;
    revisarAviso();
    botonEnviar.disabled = false;
    alFinal();
    campoTexto.focus();
  }
}

/* El campo crece con lo que se escribe, hasta cierto punto. */
function ajustarAlto() {
  campoTexto.style.height = "auto";
  campoTexto.style.height = Math.min(campoTexto.scrollHeight, 140) + "px";
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

async function cargarConversacion() {
  mensajes.textContent = "";

  /* Primero lo ya anotado, para saber qué propuestas están cumplidas. */
  try {
    const formulario = await pedir("/api/clientes/" + idCliente + "/formulario");
    yaAnotado = {};
    formulario.valores.forEach(function (valor) {
      yaAnotado[valor.celda] = valor.valor;
    });
  } catch (error) {
    yaAnotado = {};
  }

  try {
    const anteriores = await pedir("/api/clientes/" + idCliente + "/chat");
    if (anteriores.length === 0) {
      mostrarVacio();
      return;
    }
    anteriores.forEach(dibujarMensaje);
    alFinal();
    revisarAviso();
  } catch (error) {
    mostrarVacio();
  }
}

async function arrancar() {
  try {
    const quien = await pedir("/api/rentai");
    disponible = quien.disponible;
    estado.textContent = quien.disponible ? "" : quien.motivo;
    caja.classList.toggle("rentai-apagada", !quien.disponible);
  } catch (error) {
    disponible = false;
  }

  if (!disponible) {
    campoTexto.disabled = true;
    botonEnviar.disabled = true;
    campoTexto.placeholder = "RentAI está apagada";
  }

  await cargarConversacion();

  if (estabaAbierta()) abrir();
}

botonAbrir.addEventListener("click", alternar);
botonMinimizar.addEventListener("click", cerrar);
botonEnviar.addEventListener("click", enviar);
campoTexto.addEventListener("input", ajustarAlto);
campoTexto.addEventListener("keydown", function (evento) {
  /* Enter manda; Mayúsculas+Enter hace un renglón nuevo. */
  if (evento.key === "Enter" && !evento.shiftKey) {
    evento.preventDefault();
    enviar();
  }
});
botonLimpiar.addEventListener("click", async function () {
  const seguro = window.confirm(
    "¿Borrar toda la charla con RentAI sobre este cliente?\n\n"
    + "Los valores que ya anotó NO se borran."
  );
  if (!seguro) return;
  try {
    await pedir("/api/clientes/" + idCliente + "/chat", { method: "DELETE" });
    mensajes.textContent = "";
    mostrarVacio();
  } catch (error) {
    mostrarError(error.message);
  }
});
document.addEventListener("keydown", function (evento) {
  if (evento.key === "Escape" && !caja.classList.contains("rentai-cerrada")) {
    cerrar();
  }
});

arrancar();

})();
