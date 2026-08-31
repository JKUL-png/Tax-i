/* ==========================================================
   Pantalla de un cliente: el perfil, los avisos y el historial.

   El id del cliente viene en la dirección: /cliente?id=3

   Este archivo es el que va primero: define el id y las cajas de aviso
   que los demás archivos de la pantalla necesitan. JavaScript plano,
   sin librerías.
   ========================================================== */

const idCliente = new URLSearchParams(window.location.search).get("id");

const tituloNombre = document.getElementById("nombre-cliente");
const lineaDatos = document.getElementById("datos-cliente");
const aviso = document.getElementById("aviso");

/* El cliente que se está viendo, tal como lo mandó el servidor. Lo
   guardan aquí las otras secciones para no volver a pedirlo. */
let clienteActual = null;


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

/* El cómo está en comun.js. Aquí solo se dice en cuál caja. */
function mostrarAviso(texto, tipo) { avisarEn(aviso, texto, tipo); }
function ocultarAviso() { ocultarAvisoEn(aviso); }


/* ----------------------------------------------------------
   El perfil: la foto de conjunto

   Todo lo de arriba se llena de una sola vez, con lo que ya se pidió
   para las otras secciones. La idea es que al entrar a un cliente el
   contador vea cuándo vence, cuánto le falta y qué puede hacer, sin
   tener que abrir una sola sección.
   ---------------------------------------------------------- */

const perfilFecha = document.getElementById("perfil-fecha");
const perfilPlazo = document.getElementById("perfil-plazo");
const perfilAvance = document.getElementById("perfil-avance");
const perfilFaltan = document.getElementById("perfil-faltan");
const perfilDocumentos = document.getElementById("perfil-documentos");
const perfilPendientes = document.getElementById("perfil-pendientes");
const perfilListaFaltantes = document.getElementById("perfil-lista-faltantes");

/* Cuántos faltantes se nombran arriba antes de decir "y N más". Más de
   seis y la cabecera deja de ser un vistazo. */
const FALTANTES_QUE_SE_NOMBRAN = 6;

async function cargarCliente() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente);
    if (!respuesta.ok) throw new Error();
    clienteActual = await respuesta.json();

    tituloNombre.textContent = clienteActual.nombre;
    document.title = clienteActual.nombre + " · Tax-i";

    lineaDatos.textContent = "Cédula termina en " + clienteActual.dos_digitos;

    pintarVencimiento(clienteActual.fecha_vencimiento);
  } catch (e) {
    tituloNombre.textContent = "No se encontró el cliente";
    lineaDatos.textContent = "";
  }
}

/* La fecha en palabras y cuántos días faltan, con el mismo color que en
   la lista de clientes. Que sea el mismo color en los dos sitios es lo
   que hace que se pueda confiar en el color. */
function pintarVencimiento(fecha) {
  const plazo = etiquetaDePlazo(fecha);
  perfilFecha.textContent = fecha ? fechaEnPalabras(fecha) : "Sin fecha";
  perfilPlazo.textContent = plazo.texto;
  perfilPlazo.className = "etiqueta " + plazo.clase;
}

/* Lo llama el checklist cada vez que cambia algo, para que las cifras de
   arriba no se queden viejas. */
function pintarAvanceEnPerfil(renglones) {
  const total = renglones.length;
  const recibidos = renglones.filter(function (r) {
    return r.estado === "recibido";
  }).length;

  perfilAvance.textContent = total === 0 ? "—" : recibidos + " / " + total;

  const faltantes = renglones.filter(function (r) {
    return r.estado !== "recibido";
  });

  if (total === 0) {
    perfilFaltan.textContent = "sin checklist";
  } else if (faltantes.length === 0) {
    perfilFaltan.textContent = "no falta ninguno";
  } else {
    perfilFaltan.textContent = faltantes.length === 1
      ? "falta 1 documento"
      : "faltan " + faltantes.length + " documentos";
  }

  pintarFaltantes(faltantes);
}

function pintarFaltantes(faltantes) {
  perfilListaFaltantes.innerHTML = "";

  if (faltantes.length === 0) {
    perfilPendientes.className = "perfil-pendientes oculto";
    return;
  }

  faltantes.slice(0, FALTANTES_QUE_SE_NOMBRAN).forEach(function (renglon) {
    const item = document.createElement("li");
    item.textContent = renglon.titulo;
    perfilListaFaltantes.appendChild(item);
  });

  if (faltantes.length > FALTANTES_QUE_SE_NOMBRAN) {
    const mas = document.createElement("li");
    mas.className = "perfil-mas";
    mas.textContent =
      "y " + (faltantes.length - FALTANTES_QUE_SE_NOMBRAN) + " más";
    perfilListaFaltantes.appendChild(mas);
  }

  perfilPendientes.className = "perfil-pendientes";
}

/* Lo llama la lista de documentos. */
function pintarConteoEnPerfil(cuantos) {
  perfilDocumentos.textContent = cuantos;
}


/* ----------------------------------------------------------
   Pasar de un cliente a otro sin volver a la lista

   Se pide la lista completa una vez y se busca en qué puesto va este.
   La lista viene ordenada por vencimiento, así que "siguiente" es el
   que vence después: es el orden en que se revisan en temporada.
   ---------------------------------------------------------- */

async function cargarVecinos() {
  try {
    const respuesta = await fetch("/api/clientes");
    if (!respuesta.ok) return;
    const clientes = await respuesta.json();

    const donde = clientes.findIndex(function (c) {
      return String(c.id) === String(idCliente);
    });
    if (donde === -1) return;

    document.getElementById("perfil-posicion").textContent =
      (donde + 1) + " de " + clientes.length;

    enlazarVecino("cliente-anterior", clientes[donde - 1], "← ");
    enlazarVecino("cliente-siguiente", clientes[donde + 1], "", " →");
  } catch (e) {
    // Sin vecinos no pasa nada: los enlaces se quedan escondidos.
  }
}

function enlazarVecino(id, vecino, antes, despues) {
  const enlace = document.getElementById(id);
  if (!vecino) return;
  enlace.href = "/cliente?id=" + vecino.id;
  enlace.textContent = (antes || "") + vecino.nombre + (despues || "");
  enlace.title = "Ir a " + vecino.nombre;
  enlace.classList.remove("oculto");
}


/* ----------------------------------------------------------
   Historial de actividad

   Qué se subió, qué se marcó y qué se borró. Lo arma el servidor con la
   frase en español ya hecha (ver app/bitacora.py), así que aquí solo
   hay que pintarlo.
   ---------------------------------------------------------- */

const listaActividad = document.getElementById("lista-actividad");
const conteoHistorial = document.getElementById("conteo-historial");

async function cargarHistorial() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/bitacora");
    if (!respuesta.ok) throw new Error();
    dibujarHistorial(await respuesta.json());
  } catch (e) {
    listaActividad.innerHTML =
      '<li class="vacio">No se pudo cargar el historial.</li>';
  }
}

function dibujarHistorial(anotaciones) {
  listaActividad.innerHTML = "";
  conteoHistorial.textContent =
    anotaciones.length > 0 ? "(" + anotaciones.length + ")" : "";

  if (anotaciones.length === 0) {
    const vacio = document.createElement("li");
    vacio.className = "vacio";
    vacio.textContent = "Todavía no ha pasado nada con este cliente.";
    listaActividad.appendChild(vacio);
    return;
  }

  anotaciones.forEach(function (anotacion) {
    const renglon = document.createElement("li");
    renglon.className = "actividad";
    if (anotacion.tono) renglon.classList.add("actividad-" + anotacion.tono);

    const cuando = document.createElement("span");
    cuando.className = "actividad-cuando cifra";
    cuando.textContent = fechaHoraEnPalabras(anotacion.fecha_hora);

    const que = document.createElement("span");
    que.className = "actividad-que";
    que.textContent = anotacion.frase;

    renglon.appendChild(cuando);
    renglon.appendChild(que);

    // El nombre del archivo o del renglón, cuando fue uno solo.
    if (anotacion.detalle) {
      const cual = document.createElement("span");
      cual.className = "actividad-detalle";
      cual.textContent = anotacion.detalle;
      renglon.appendChild(cual);
    }

    listaActividad.appendChild(renglon);
  });
}


/* ----------------------------------------------------------
   Preguntar antes de borrar

   Reemplaza al confirm() del navegador porque aquí hace falta decir
   cuántos archivos son y de qué cliente, con los nombres a la vista.
   Devuelve una promesa que da true o false.
   ---------------------------------------------------------- */

const cajaConfirmar = document.getElementById("confirmar");
const confirmarTitulo = document.getElementById("confirmar-titulo");
const confirmarFrase = document.getElementById("confirmar-frase");
const confirmarCliente = document.getElementById("confirmar-cliente");
const confirmarLista = document.getElementById("confirmar-lista");
const confirmarNota = document.getElementById("confirmar-nota");
const confirmarSi = document.getElementById("confirmar-si");
const confirmarNo = document.getElementById("confirmar-no");

/* Cuántos nombres se muestran antes de resumir con "y N más". */
const NOMBRES_EN_CONFIRMACION = 10;

let decidir = null;

function preguntar(opciones) {
  confirmarTitulo.textContent = opciones.titulo || "Confirmar";
  confirmarFrase.textContent = opciones.frase || "";
  confirmarCliente.textContent = opciones.cliente || "";
  confirmarNota.textContent = opciones.nota || "";

  confirmarLista.innerHTML = "";
  const nombres = opciones.nombres || [];
  nombres.slice(0, NOMBRES_EN_CONFIRMACION).forEach(function (nombre) {
    const item = document.createElement("li");
    item.textContent = nombre;
    confirmarLista.appendChild(item);
  });
  if (nombres.length > NOMBRES_EN_CONFIRMACION) {
    const mas = document.createElement("li");
    mas.className = "perfil-mas";
    mas.textContent = "y " + (nombres.length - NOMBRES_EN_CONFIRMACION) + " más";
    confirmarLista.appendChild(mas);
  }

  cajaConfirmar.className = "visor";
  // El botón que se enfoca es Cancelar, no Eliminar: si alguien viene
  // dándole a la barra espaciadora, que no borre nada sin querer.
  confirmarNo.focus();

  return new Promise(function (resolver) { decidir = resolver; });
}

function cerrarConfirmacion(respuesta) {
  cajaConfirmar.className = "visor oculto";
  if (decidir) {
    decidir(respuesta);
    decidir = null;
  }
}

confirmarSi.addEventListener("click", function () { cerrarConfirmacion(true); });
confirmarNo.addEventListener("click", function () { cerrarConfirmacion(false); });
cajaConfirmar.addEventListener("click", function (evento) {
  // Clic por fuera de la caja: se cancela. Nunca se confirma por fuera.
  if (evento.target === cajaConfirmar) cerrarConfirmacion(false);
});
document.addEventListener("keydown", function (evento) {
  if (evento.key === "Escape" && !cajaConfirmar.classList.contains("oculto")) {
    cerrarConfirmacion(false);
  }
});


/* ----------------------------------------------------------
   Aviso de cómo está configurado el programa
   ---------------------------------------------------------- */

async function cargarConfiguracion() {
  const caja = document.getElementById("aviso-modo");
  try {
    const respuesta = await fetch("/api/configuracion");
    if (!respuesta.ok) return;
    const config = await respuesta.json();

    caja.textContent = config.motivo;
    caja.className = config.ia_disponible
      ? "aviso-modo aviso-modo-ia"
      : "aviso-modo";
  } catch (e) {
    // Si no se puede leer, no se muestra nada. No es crítico.
  }
}


/* ----------------------------------------------------------
   Recordar qué secciones quedaron abiertas

   La pantalla es larga, así que las secciones se pliegan. Si el contador
   deja abierta la de documentos, la próxima vez que entre a un cliente
   debería encontrarla abierta: no tiene por qué volver a abrirla cada vez.

   Se guarda en el navegador (localStorage), que es de este computador y
   no sale de aquí. Solo se guarda cuál sección está abierta: ningún dato
   de ningún cliente.
   ---------------------------------------------------------- */

function recordarPlegables() {
  const plegables = document.querySelectorAll(".plegable");

  plegables.forEach(function (plegable) {
    const llave = "abierto:" + plegable.id;

    /* Lo guardado manda sobre lo que diga el HTML. */
    let guardado = null;
    try {
      guardado = window.localStorage.getItem(llave);
    } catch (error) {
      /* Hay navegadores que no dejan guardar nada (modo privado). Se
         sigue sin recordar, que no es grave. */
    }
    if (guardado === "si") plegable.open = true;
    if (guardado === "no") plegable.open = false;

    plegable.addEventListener("toggle", function () {
      try {
        window.localStorage.setItem(llave, plegable.open ? "si" : "no");
      } catch (error) { /* igual que arriba */ }
    });
  });
}

/* Lleva a una sección desde los botones del perfil.

   Hay que hacer tres cosas y en este orden:

     1. Cambiar a la pestaña donde vive la sección.
     2. Abrir la sección, que puede estar plegada.
     3. Bajar hasta ella.

   El paso 1 es el que faltaba. Cuando la pantalla del cliente se partió
   en tres pestañas, "Generar el mensaje para el cliente" y "Exportar el
   resumen" se quedaron apuntando a una sección que quedó dentro de la
   pestaña de Historial. El botón sí abría el <details>... adentro de un
   panel con el atributo `hidden`, así que en pantalla no pasaba nada de
   nada. Los dos botones llevaban rotos desde entonces.

   `destino` es opcional: si se pasa, se baja hasta ese elemento en vez
   de hasta el principio de la sección. Es lo que hace que "Exportar el
   resumen" caiga en el resumen y no en el mensaje, estando los dos en
   la misma sección. */
function irASeccion(vista, idPlegable, idDestino) {
  /* La pestaña la cambia riel.js, que es quien las maneja. Si por lo que
     sea no está cargado, se sigue: abrir y bajar todavía sirve. */
  if (window.RielTaxi && window.RielTaxi.mostrarVista) {
    window.RielTaxi.mostrarVista(vista);
  }

  const plegable = document.getElementById(idPlegable);
  if (!plegable) return;
  plegable.open = true;

  const destino = (idDestino && document.getElementById(idDestino)) || plegable;
  destino.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("perfil-subir").addEventListener("click", function () {
  irASeccion("documentos", "plegable-subir");
});
document.getElementById("perfil-mensaje").addEventListener("click", function () {
  irASeccion("historial", "plegable-exportar", "tarjeta-mensaje");
});
document.getElementById("perfil-exportar").addEventListener("click", function () {
  irASeccion("historial", "plegable-exportar", "tarjeta-resumen");
});
