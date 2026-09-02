/* ==========================================================
   Los documentos ya confirmados del cliente.

   Se pueden marcar con casillas y eliminar varios de un golpe. El
   borrado SIEMPRE pregunta antes, diciendo cuántos archivos son y de
   qué cliente: borrar los soportes de alguien en plena temporada es un
   daño real, y el archivo se va a la papelera, no al vacío.

   Aquí adentro va también el visor, porque es la ventana que abre un
   documento de esta misma lista.
   ========================================================== */

const contenedorLista = document.getElementById("lista-documentos");
const conteo = document.getElementById("conteo");
const avisoDocumentos = document.getElementById("aviso-documentos");
const barraDocumentos = document.getElementById("barra-documentos");
const casillaTodosDocs = document.getElementById("documentos-todos");
const rotuloSeleccionDocs = document.getElementById("documentos-seleccion");
const botonEliminarDocs = document.getElementById("documentos-eliminar");

/* Los renglones del checklist del cliente. Se guardan aquí porque la
   lista de documentos los necesita para armar el selector de asignación. */
let renglonesDelCliente = [];

/* Los documentos que se están mostrando y cuáles están marcados.
   Se guardan los ids en un Set: buscar en un Set es inmediato y no
   se pueden repetir. */
let documentosDelCliente = [];
let marcados = new Set();

function mostrarAvisoDocumentos(texto, tipo) {
  avisarEn(avisoDocumentos, texto, tipo);
}


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

/* En qué va la lectura de un documento, en una etiqueta de una línea.

   Son los cuatro estados de la fila. El de fallo dice POR QUÉ falló: sin
   el motivo, el contador ve una marca roja y no sabe si el archivo está
   dañado, si se acabó el cupo o si el programa tiene un error. */
const TEXTOS_DE_LECTURA = {
  pendiente: ["Sin leer", "etiqueta-neutra"],
  leyendo:   ["Leyéndose…", "etiqueta-alerta"],
  listo:     ["Leído", "etiqueta-exito"],
  fallo:     ["No se pudo leer", "etiqueta-error"]
};

function etiquetaDeLectura(documento) {
  const estado = documento.estado_lectura || "pendiente";
  const [texto, clase] = TEXTOS_DE_LECTURA[estado]
    || TEXTOS_DE_LECTURA.pendiente;

  const linea = document.createElement("p");
  linea.className = "documento-detalle";

  const marca = document.createElement("span");
  marca.className = "etiqueta " + clase;
  marca.textContent = texto;
  linea.appendChild(marca);

  if (estado === "fallo" && documento.motivo_lectura) {
    const motivo = document.createElement("span");
    motivo.className = "documento-motivo";
    motivo.textContent = " " + documento.motivo_lectura;
    linea.appendChild(motivo);
  }
  return linea;
}


function dibujarDocumentos(documentos) {
  documentosDelCliente = documentos;

  // Al recargar, se olvidan las marcas de los documentos que ya no están.
  marcados = new Set(
    Array.from(marcados).filter(function (id) {
      return documentos.some(function (d) { return d.id === id; });
    })
  );

  contenedorLista.innerHTML = "";
  conteo.textContent = documentos.length > 0 ? "(" + documentos.length + ")" : "";
  pintarConteoEnPerfil(documentos.length);

  if (documentos.length === 0) {
    barraDocumentos.className = "revision-barra oculto";
    const vacio = document.createElement("div");
    vacio.className = "vacio";
    vacio.textContent =
      "Todavía no hay documentos de este cliente. Suba los primeros arriba.";
    contenedorLista.appendChild(vacio);
    return;
  }

  barraDocumentos.className = "revision-barra";
  documentos.forEach(function (documento) {
    contenedorLista.appendChild(dibujarDocumento(documento));
  });
  refrescarSeleccionDocs();
}

function dibujarDocumento(documento) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "documento";

  /* --- Casilla para marcarlo --- */
  const casilla = document.createElement("input");
  casilla.type = "checkbox";
  casilla.className = "documento-casilla";
  casilla.checked = marcados.has(documento.id);
  casilla.setAttribute("aria-label", "Marcar " + documento.nombre_original);
  casilla.addEventListener("change", function () {
    if (casilla.checked) {
      marcados.add(documento.id);
    } else {
      marcados.delete(documento.id);
    }
    tarjeta.classList.toggle("documento-marcado", casilla.checked);
    refrescarSeleccionDocs();
  });
  tarjeta.classList.toggle("documento-marcado", casilla.checked);

  /* --- Etiqueta del tipo (PDF, Foto, XML) --- */
  const tipo = document.createElement("span");
  tipo.className = "documento-tipo";
  tipo.textContent = documento.tipo;

  /* --- Nombre y detalles --- */
  const datos = document.createElement("div");
  datos.className = "documento-datos";

  const nombre = document.createElement("p");
  nombre.className = "documento-nombre";
  // textContent y no innerHTML: si el archivo se llama "<script>.pdf",
  // se muestra como texto y no se ejecuta nada.
  nombre.textContent = documento.nombre_original;

  const detalle = document.createElement("p");
  detalle.className = "documento-detalle";
  let texto = pesoEnPalabras(documento.tamano) + " · " +
              fechaHoraEnPalabras(documento.subido_en);
  if (documento.venia_en_zip) {
    texto += " · venía en " + documento.venia_en_zip;
  }
  detalle.textContent = texto;

  datos.appendChild(nombre);
  datos.appendChild(detalle);
  datos.appendChild(etiquetaDeLectura(documento));

  /* --- A qué renglón del checklist pertenece --- */
  const asignacion = document.createElement("div");
  asignacion.className = "documento-asignacion";

  /* Un campo con búsqueda, no un <select> del navegador: con los
     renglones que salen de la exógena la lista se sale de la pantalla.
     Ver static/selector-renglon.js. */
  const selector = SelectorRenglon.crear({
    renglones: renglonesDelCliente,
    elegido: documento.renglon_id || null,
    etiqueta: "Asignar a un renglón del checklist",
    alElegir: function (id) {
      asignarDocumento(documento.id, id || null);
    }
  });

  asignacion.appendChild(selector.elemento);

  // Si el programa cree saber a qué renglón va, lo propone. La sugerencia
  // sale del nombre del archivo, con código: no la hizo ninguna IA.
  if (!documento.renglon_id && documento.sugerencia) {
    const sugerido = renglonesDelCliente.find(function (r) {
      return r.id === documento.sugerencia;
    });
    if (sugerido) {
      const propuesta = document.createElement("button");
      propuesta.type = "button";
      propuesta.className = "sugerencia";
      propuesta.textContent = "¿Es \"" + sugerido.titulo + "\"?";
      propuesta.title = "Sugerencia por el nombre del archivo. Confirme usted.";
      propuesta.addEventListener("click", function () {
        asignarDocumento(documento.id, sugerido.id);
      });
      asignacion.appendChild(propuesta);
    }
  }

  /* --- Acciones --- */
  const acciones = document.createElement("div");
  acciones.className = "documento-acciones";

  const botonVer = document.createElement("button");
  botonVer.type = "button";
  botonVer.className = "boton-texto";
  botonVer.textContent = "Ver el documento";
  botonVer.addEventListener("click", function () {
    abrirVisor(documento);
  });

  const botonEliminar = document.createElement("button");
  botonEliminar.type = "button";
  botonEliminar.className = "boton-texto boton-texto-peligro";
  botonEliminar.textContent = "Mover a la papelera";
  botonEliminar.addEventListener("click", function () {
    eliminarDocumentos([documento]);
  });

  acciones.appendChild(botonVer);
  acciones.appendChild(botonEliminar);

  const arriba = document.createElement("div");
  arriba.className = "documento-arriba";
  arriba.appendChild(casilla);
  arriba.appendChild(tipo);
  arriba.appendChild(datos);
  arriba.appendChild(acciones);

  tarjeta.appendChild(arriba);
  tarjeta.appendChild(asignacion);
  return tarjeta;
}


/* ----------------------------------------------------------
   Marcar varios
   ---------------------------------------------------------- */

/* Pone al día el rótulo, el botón y la casilla de "marcar todos". */
function refrescarSeleccionDocs() {
  const cuantos = marcados.size;
  const total = documentosDelCliente.length;

  rotuloSeleccionDocs.textContent = cuantos === 0
    ? "Marcar todos"
    : contar(cuantos, "marcado", "marcados");

  botonEliminarDocs.disabled = cuantos === 0;
  botonEliminarDocs.textContent = cuantos === 0
    ? "Mover a la papelera los marcados"
    : "Mover a la papelera " + contar(cuantos, "documento", "documentos");

  casillaTodosDocs.checked = total > 0 && cuantos === total;
  // "Algunos marcados": el cuadradito a medias, ni vacío ni con chulo.
  casillaTodosDocs.indeterminate = cuantos > 0 && cuantos < total;
}

casillaTodosDocs.addEventListener("change", function () {
  marcados = casillaTodosDocs.checked
    ? new Set(documentosDelCliente.map(function (d) { return d.id; }))
    : new Set();
  dibujarDocumentos(documentosDelCliente);
});

botonEliminarDocs.addEventListener("click", function () {
  const elegidos = documentosDelCliente.filter(function (d) {
    return marcados.has(d.id);
  });
  eliminarDocumentos(elegidos);
});


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function cargarDocumentos() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/documentos");
    if (!respuesta.ok) throw new Error();
    dibujarDocumentos(await respuesta.json());
  } catch (e) {
    contenedorLista.innerHTML =
      '<div class="vacio">No se pudieron cargar los documentos.</div>';
  }
}

/* Elimina uno o varios documentos. SIEMPRE pregunta antes.

   La pregunta dice cuántos son y de qué cliente, con los nombres a la
   vista. Es la condición para que exista el borrado en lote: un mal
   clic aquí borra los soportes de alguien en plena temporada.

   El servidor recibe la dirección con el cliente adentro y comprueba
   por su cuenta que cada documento sea de ese cliente. */
async function eliminarDocumentos(elegidos) {
  if (!elegidos || elegidos.length === 0) return;

  const cuantos = elegidos.length;
  const quien = clienteActual ? clienteActual.nombre : "este cliente";

  const seguro = await preguntar({
    titulo: cuantos === 1
      ? "Mover un documento a la papelera"
      : "Mover documentos a la papelera",
    frase: "Se van a mover a la papelera " +
           contar(cuantos, "archivo", "archivos") + ":",
    cliente: "Del expediente de " + quien,
    nombres: elegidos.map(function (d) { return d.nombre_original; }),
    nota: "Los archivos salen del expediente y quedan en la carpeta " +
          "datos/papelera de este computador, por si hubo un error. " +
          "El movimiento queda anotado en el historial del cliente."
  });
  if (!seguro) return;

  const respuesta = await fetch(
    "/api/clientes/" + idCliente + "/documentos/eliminar",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: elegidos.map(function (d) { return d.id; }) })
    }
  );

  if (!respuesta.ok) {
    mostrarAvisoDocumentos(await textoDelError(respuesta), "error");
    return;
  }

  const resultado = await respuesta.json();
  marcados = new Set();

  let texto = "Se movió a la papelera ";
  if (resultado.borrados !== 1) texto = "Se movieron a la papelera ";
  texto += contar(resultado.borrados, "documento", "documentos") + ".";
  if (resultado.ignorados > 0) {
    // Si esto pasa, la pantalla mandó ids que no eran de este cliente.
    // El servidor los rechazó, que es justamente para lo que está.
    texto += " " + contar(resultado.ignorados, "archivo no era", "archivos no eran") +
             " de este cliente y no se tocó.";
  }
  mostrarAvisoDocumentos(texto, "exito");

  cargarDocumentos();
  cargarChecklist();
  cargarHistorial();
  refrescarMensaje();
}


/* ----------------------------------------------------------
   Asignar un documento a un renglón del checklist
   ---------------------------------------------------------- */

async function asignarDocumento(idDocumento, idRenglon) {
  const respuesta = await fetch("/api/documentos/" + idDocumento, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      renglon_id: idRenglon ? Number(idRenglon) : null
    })
  });

  if (!respuesta.ok) {
    mostrarAvisoDocumentos(await textoDelError(respuesta), "error");
    cargarDocumentos();   // se devuelve a como estaba
    return;
  }

  // Asignar un documento marca su renglón como recibido, así que hay
  // que recargar las dos listas y rehacer el mensaje.
  await cargarChecklist();
  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
}


/* ==========================================================
   Visor de documentos

   Abre el archivo encima de la pantalla, sin salir del cliente.
   Cada tipo se muestra a su manera: los PDF y las fotos los dibuja
   el navegador, el XML y los Excel los prepara el servidor.
   ========================================================== */

const visor = document.getElementById("visor");
const visorTitulo = document.getElementById("visor-titulo");
const visorContenido = document.getElementById("visor-contenido");
const visorAbrir = document.getElementById("visor-abrir");
const visorCerrar = document.getElementById("visor-cerrar");

function cerrarVisor() {
  visor.className = "visor oculto";
  visorContenido.innerHTML = "";   // suelta el PDF o la imagen de la memoria
}

visorCerrar.addEventListener("click", cerrarVisor);

// Clic en el fondo oscuro: cierra. Clic dentro de la caja: no.
visor.addEventListener("click", function (evento) {
  if (evento.target === visor) cerrarVisor();
});

document.addEventListener("keydown", function (evento) {
  if (evento.key === "Escape" && !visor.classList.contains("oculto")) {
    cerrarVisor();
  }
});

/* Dibuja un mensaje simple dentro del visor. */
function mensajeEnVisor(texto) {
  const parrafo = document.createElement("p");
  parrafo.className = "visor-mensaje";
  parrafo.textContent = texto;
  return parrafo;
}

/* Los campos que el código sacó de un XML de factura electrónica. */
function bloqueDeLectura(leido) {
  const caja = document.createElement("div");
  caja.className = "lectura-xml";

  const titulo = document.createElement("p");
  titulo.className = "lectura-titulo";
  titulo.textContent = "Leído del archivo (exacto, sin IA)";
  caja.appendChild(titulo);

  const NOMBRES = {
    numero: "Número", fecha: "Fecha", cufe: "CUFE",
    emisor: "Emisor", nit_emisor: "NIT del emisor",
    receptor: "Receptor", total: "Total", moneda: "Moneda"
  };

  const lista = document.createElement("dl");
  lista.className = "lectura-campos";
  Object.keys(leido).forEach(function (campo) {
    const nombre = document.createElement("dt");
    nombre.textContent = NOMBRES[campo] || campo;
    const valor = document.createElement("dd");
    valor.textContent = leido[campo];
    lista.appendChild(nombre);
    lista.appendChild(valor);
  });
  caja.appendChild(lista);
  return caja;
}

async function abrirVisor(documento) {
  visorTitulo.textContent = documento.nombre_original;
  visorAbrir.href = "/api/documentos/" + documento.id + "/archivo";
  visorContenido.innerHTML = "";
  visorContenido.appendChild(mensajeEnVisor("Cargando…"));
  visor.className = "visor";

  let datos;
  try {
    const respuesta = await fetch("/api/documentos/" + documento.id + "/vista");
    if (!respuesta.ok) throw new Error();
    datos = await respuesta.json();
  } catch (e) {
    visorContenido.innerHTML = "";
    visorContenido.appendChild(
      mensajeEnVisor("No se pudo cargar la vista del documento.")
    );
    return;
  }

  visorContenido.innerHTML = "";

  if (datos.vista === "pdf") {
    // El navegador trae su propio lector de PDF.
    const marco = document.createElement("iframe");
    marco.className = "visor-pdf";
    marco.src = datos.url;
    marco.title = documento.nombre_original;
    visorContenido.appendChild(marco);

  } else if (datos.vista === "imagen") {
    const imagen = document.createElement("img");
    imagen.className = "visor-imagen";
    imagen.src = datos.url;
    imagen.alt = documento.nombre_original;
    visorContenido.appendChild(imagen);

  } else if (datos.vista === "tabla") {
    if (datos.recortado) {
      visorContenido.appendChild(mensajeEnVisor(
        "Mostrando las primeras " + datos.filas.length + " filas de " +
        datos.total_filas + ". Para verlo completo, abra el archivo aparte."
      ));
    }
    const envoltura = document.createElement("div");
    envoltura.className = "tabla-envoltura";
    const tabla = document.createElement("table");
    tabla.className = "tabla-vista";

    datos.filas.forEach(function (fila, numero) {
      const renglon = document.createElement("tr");
      fila.forEach(function (casilla) {
        // La primera fila se dibuja como encabezado.
        const celda = document.createElement(numero === 0 ? "th" : "td");
        celda.textContent = casilla;
        renglon.appendChild(celda);
      });
      tabla.appendChild(renglon);
    });

    envoltura.appendChild(tabla);
    visorContenido.appendChild(envoltura);

  } else if (datos.vista === "texto") {
    if (datos.leido) {
      visorContenido.appendChild(bloqueDeLectura(datos.leido));
    }
    if (datos.recortado) {
      visorContenido.appendChild(mensajeEnVisor(
        "El archivo es largo: se muestra solo el comienzo."
      ));
    }
    const bloque = document.createElement("pre");
    bloque.className = "visor-texto";
    bloque.textContent = datos.texto;
    visorContenido.appendChild(bloque);

  } else {
    visorContenido.appendChild(mensajeEnVisor(
      datos.motivo || "Este archivo no se puede ver aquí."
    ));
    const enlace = document.createElement("a");
    enlace.className = "boton";
    enlace.href = datos.url;
    enlace.target = "_blank";
    enlace.rel = "noopener";
    enlace.textContent = "Abrir el archivo aparte";
    visorContenido.appendChild(enlace);
  }
}


/* ==========================================================
   La fila de lectura

   Los documentos se leen UNA vez y lo que se les saca queda guardado en
   la base. Después RentAI contesta con esas filas y no vuelve a leer —ni
   a pagar— los mismos documentos.

   La lectura corre en otro hilo del servidor: el contador aprieta el
   botón y sigue trabajando. Esta parte solo pregunta cada tanto en qué
   va y repinta la lista.
   ========================================================== */

const cajaCola = document.getElementById("caja-cola");
const colaTexto = document.getElementById("cola-texto");
const botonProcesar = document.getElementById("cola-procesar");
const marcaAutomatico = document.getElementById("cola-automatico");

/* Cada cuánto se le pregunta al servidor mientras está trabajando. Dos
   segundos: suficiente para que se vea vivo, sin llenar de peticiones. */
const CADA_CUANTO = 2000;
let relojDeCola = null;

async function preguntarPorLaCola(repintar) {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/datos");
    if (!respuesta.ok) return null;
    const datos = await respuesta.json();
    mostrarEstadoDeCola(datos.estado);
    if (repintar) cargarDocumentos();
    return datos.estado;
  } catch (e) {
    return null;
  }
}

function mostrarEstadoDeCola(estado) {
  if (!cajaCola || !estado) return;

  const cuenta = estado.estados || {};
  const sinLeer = estado.sin_leer || 0;
  const total = (cuenta.pendiente || 0) + (cuenta.leyendo || 0)
              + (cuenta.listo || 0) + (cuenta.fallo || 0);

  /* Sin documentos no hay nada que decir. */
  cajaCola.classList.toggle("oculto", total === 0);
  if (total === 0) return;

  const partes = [];
  if (cuenta.leyendo) {
    partes.push("Leyendo " + contar(cuenta.leyendo, "documento", "documentos") + "…");
  }
  if (sinLeer - (cuenta.leyendo || 0) > 0) {
    partes.push(contar(sinLeer - (cuenta.leyendo || 0), "documento sin leer",
                       "documentos sin leer"));
  }
  if (cuenta.listo) {
    partes.push(contar(cuenta.listo, "leído", "leídos"));
  }
  if (cuenta.fallo) {
    partes.push(contar(cuenta.fallo, "no se pudo leer", "no se pudieron leer"));
  }

  colaTexto.textContent = partes.join(" · ");
  botonProcesar.disabled = sinLeer === 0;
  botonProcesar.textContent = sinLeer === 0
    ? "Todo leído"
    : "Procesar " + contar(sinLeer, "pendiente", "pendientes");
}

/* Mientras la fila trabaja se pregunta cada dos segundos. Cuando ya no
   queda nada por leer, se deja de preguntar: sin esto el programa
   seguiría haciendo peticiones toda la tarde sin motivo. */
function vigilarLaCola() {
  clearInterval(relojDeCola);
  relojDeCola = setInterval(async function () {
    const estado = await preguntarPorLaCola(true);
    if (!estado || (estado.sin_leer || 0) === 0) {
      clearInterval(relojDeCola);
      relojDeCola = null;
    }
  }, CADA_CUANTO);
}

if (botonProcesar) {
  botonProcesar.addEventListener("click", async function () {
    botonProcesar.disabled = true;
    colaTexto.textContent = "Poniendo a leer los documentos…";
    try {
      const respuesta = await fetch(
        "/api/clientes/" + idCliente + "/datos/procesar", { method: "POST" }
      );
      if (!respuesta.ok) throw new Error(await textoDelError(respuesta));
      const datos = await respuesta.json();
      mostrarEstadoDeCola(datos.estado);
      vigilarLaCola();
    } catch (e) {
      mostrarAviso(e.message || "No se pudo poner a leer los documentos.",
                   "error");
      preguntarPorLaCola(false);
    }
  });
}

if (marcaAutomatico) {
  marcaAutomatico.addEventListener("change", async function () {
    try {
      const respuesta = await fetch("/api/cola/automatico", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prendido: marcaAutomatico.checked })
      });
      if (!respuesta.ok) throw new Error(await textoDelError(respuesta));
      const datos = await respuesta.json();
      marcaAutomatico.checked = datos.automatico;
      mostrarAviso(
        datos.automatico
          ? "Al confirmar una carga, los documentos se leerán solos."
          : "Los documentos se leerán solo cuando usted lo pida.",
        "exito"
      );
    } catch (e) {
      // Se devuelve la marca a como estaba: no quedó guardado.
      marcaAutomatico.checked = !marcaAutomatico.checked;
      mostrarAviso(e.message || "No se pudo guardar el ajuste.", "error");
    }
  });
}

/* Al abrir la pantalla se pregunta una vez, y si hay algo leyéndose se
   queda vigilando. */
async function arrancarLaCola() {
  const estado = await preguntarPorLaCola(false);
  try {
    const respuesta = await fetch("/api/cola");
    if (respuesta.ok) {
      const fila = await respuesta.json();
      if (marcaAutomatico) marcaAutomatico.checked = !!fila.automatico;
      if (fila.trabajando) vigilarLaCola();
    }
  } catch (e) {
    // Si no se puede preguntar, la pantalla funciona igual sin esto.
  }
  return estado;
}
