/* ==========================================================
   Pantalla de clientes.

   Habla con el servidor por /api/clientes y dibuja la lista.
   JavaScript plano, sin librerías: se abre y se entiende leyéndolo.
   ========================================================== */

const formulario = document.getElementById("formulario-cliente");
const campoNombre = document.getElementById("nombre");
const campoDigitos = document.getElementById("digitos");
const campoFecha = document.getElementById("fecha");
const contenedorLista = document.getElementById("lista-clientes");
const aviso = document.getElementById("aviso");


/* ----------------------------------------------------------
   Avisos arriba del formulario
   ---------------------------------------------------------- */

/* El cómo está en comun.js. Aquí solo se dice en cuál caja. */
function mostrarAviso(texto, tipo) { avisarEn(aviso, texto, tipo); }
function ocultarAviso() { ocultarAvisoEn(aviso); }


/* ----------------------------------------------------------
   Buscar, ordenar y filtrar

   La lista completa llega en una sola petición, así que todo esto se
   hace aquí en el navegador: es inmediato y no molesta al servidor.
   ---------------------------------------------------------- */

const campoBuscar = document.getElementById("buscar-cliente");
const selectorOrden = document.getElementById("orden-clientes");
const cajaFiltros = document.getElementById("filtro-estado");
const resumenFiltro = document.getElementById("resumen-filtro");
const conteoClientes = document.getElementById("conteo-clientes");

/* Cuántos días adelante cuentan como "vence pronto". Quince es el mismo
   número con el que la etiqueta de plazo se pone ámbar, para que el
   filtro y el color digan lo mismo. */
const DIAS_QUE_SON_PRONTO = 15;

/* Todos los clientes tal como llegaron, sin filtrar. */
let todosLosClientes = [];
let estadoElegido = "todos";

/* Quita tildes y mayúsculas para poder buscar "Maria" y encontrar
   "María". En una lista de nombres colombianos esto no es un lujo. */
function parejo(texto) {
  return (texto || "")
    .toString()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function cuantoFalta(cliente) {
  const total = cliente.checklist_total || 0;
  const recibidos = cliente.checklist_recibidos || 0;
  return total - recibidos;
}

function estaCompleto(cliente) {
  const total = cliente.checklist_total || 0;
  return total > 0 && cuantoFalta(cliente) === 0;
}

function vencePronto(cliente) {
  if (!cliente.fecha_vencimiento) return false;
  // Los vencidos también entran: son los más urgentes de todos.
  return diasQueFaltan(cliente.fecha_vencimiento) <= DIAS_QUE_SON_PRONTO;
}

function filtrarYOrdenar() {
  const busqueda = parejo(campoBuscar.value);

  let lista = todosLosClientes.filter(function (cliente) {
    if (busqueda) {
      const nombre = parejo(cliente.nombre);
      const digitos = cliente.dos_digitos || "";
      if (nombre.indexOf(busqueda) === -1 && digitos.indexOf(busqueda) === -1) {
        return false;
      }
    }
    if (estadoElegido === "completos") return estaCompleto(cliente);
    if (estadoElegido === "incompletos") return !estaCompleto(cliente);
    if (estadoElegido === "pronto") return vencePronto(cliente);
    return true;
  });

  lista = lista.slice().sort(comparadores[selectorOrden.value] || comparadores.vencimiento);

  dibujarLista(lista);
  contarLoQueSeVe(lista.length);
}

/* Compara nombres como los ordenaría una persona: sin importar tildes
   ni mayúsculas, y con la ñ en su sitio. */
function porNombre(a, b) {
  return a.nombre.localeCompare(b.nombre, "es", { sensitivity: "base" });
}

const comparadores = {
  vencimiento: function (a, b) {
    // Los que no tienen fecha van al final: lo urgente primero.
    if (!a.fecha_vencimiento && !b.fecha_vencimiento) return porNombre(a, b);
    if (!a.fecha_vencimiento) return 1;
    if (!b.fecha_vencimiento) return -1;
    if (a.fecha_vencimiento !== b.fecha_vencimiento) {
      return a.fecha_vencimiento < b.fecha_vencimiento ? -1 : 1;
    }
    return porNombre(a, b);
  },

  nombre: porNombre,

  faltantes: function (a, b) {
    // Más faltantes primero: son los que hay que perseguir.
    const diferencia = cuantoFalta(b) - cuantoFalta(a);
    return diferencia !== 0 ? diferencia : porNombre(a, b);
  }
};

function contarLoQueSeVe(cuantos) {
  const total = todosLosClientes.length;
  conteoClientes.textContent = total > 0 ? "(" + total + ")" : "";

  if (total === 0) { resumenFiltro.textContent = ""; return; }

  if (cuantos === total) {
    // Sin filtro puesto no hace falta decir nada, salvo lo que importa:
    // cuántos tienen algo pendiente y vencen pronto.
    const urgentes = todosLosClientes.filter(function (c) {
      return vencePronto(c) && !estaCompleto(c);
    }).length;
    resumenFiltro.textContent = urgentes === 0
      ? ""
      : "Atención: " + contar(urgentes, "cliente tiene", "clientes tienen") +
        " documentos pendientes y vencimiento a menos de " +
        DIAS_QUE_SON_PRONTO + " días.";
    return;
  }

  resumenFiltro.textContent =
    "Mostrando " + cuantos + " de " + contar(total, "cliente", "clientes") + ".";
}

campoBuscar.addEventListener("input", filtrarYOrdenar);
selectorOrden.addEventListener("change", filtrarYOrdenar);

cajaFiltros.addEventListener("click", function (evento) {
  const boton = evento.target.closest(".filtro");
  if (!boton) return;

  estadoElegido = boton.dataset.estado;
  cajaFiltros.querySelectorAll(".filtro").forEach(function (uno) {
    uno.classList.toggle("filtro-activo", uno === boton);
  });
  filtrarYOrdenar();
});


/* ----------------------------------------------------------
   Dibujar la lista
   ---------------------------------------------------------- */

function dibujarLista(clientes) {
  contenedorLista.innerHTML = "";

  if (clientes.length === 0) {
    const vacio = document.createElement("div");
    vacio.className = "vacio";
    vacio.textContent = todosLosClientes.length === 0
      ? "Todavía no hay clientes. Agregue el primero arriba."
      : "Ningún cliente coincide con lo que buscó.";
    contenedorLista.appendChild(vacio);
    return;
  }

  clientes.forEach(function (cliente) {
    contenedorLista.appendChild(dibujarCliente(cliente));
  });
}

function dibujarCliente(cliente) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "cliente";

  /* --- Nombre y cédula --- */
  const datos = document.createElement("div");
  datos.className = "cliente-datos";

  // El nombre es un enlace a la pantalla de documentos del cliente.
  const nombre = document.createElement("h3");
  nombre.className = "cliente-nombre";
  const enlaceNombre = document.createElement("a");
  enlaceNombre.href = "/cliente?id=" + cliente.id;
  enlaceNombre.textContent = cliente.nombre;
  nombre.appendChild(enlaceNombre);

  const cedula = document.createElement("p");
  cedula.className = "cliente-cedula";
  // Los dos dígitos van en letra de ancho fijo: son un número, y así
  // quedan alineados de una tarjeta a la siguiente.
  cedula.appendChild(document.createTextNode("Cédula termina en "));
  const digitos = document.createElement("span");
  digitos.className = "cifra";
  digitos.textContent = cliente.dos_digitos;
  cedula.appendChild(digitos);
  const cuantos = cliente.documentos || 0;
  cedula.appendChild(document.createTextNode(
    " · " + cuantos + (cuantos === 1 ? " documento" : " documentos")
  ));

  // Cuánto le falta del checklist: es lo que el contador quiere ver
  // de un vistazo sin tener que entrar cliente por cliente.
  const avanceCliente = document.createElement("p");
  avanceCliente.className = "cliente-avance";
  const total = cliente.checklist_total || 0;
  const recibidos = cliente.checklist_recibidos || 0;

  if (total === 0) {
    avanceCliente.textContent = "Sin checklist";
    avanceCliente.classList.add("avance-neutro");
  } else if (recibidos === total) {
    avanceCliente.textContent = "Completo: " + recibidos + " de " + total;
    avanceCliente.classList.add("avance-completo");
  } else {
    avanceCliente.textContent =
      recibidos + " de " + total + " · faltan " + (total - recibidos);
    avanceCliente.classList.add("avance-pendiente");
  }

  datos.appendChild(nombre);
  datos.appendChild(cedula);
  datos.appendChild(avanceCliente);

  /* --- Fecha de vencimiento, editable --- */
  const bloqueFecha = document.createElement("div");
  bloqueFecha.className = "cliente-fecha";

  const etiquetaCampo = document.createElement("label");
  etiquetaCampo.textContent = "Fecha de vencimiento";
  etiquetaCampo.setAttribute("for", "fecha-" + cliente.id);

  const entradaFecha = document.createElement("input");
  entradaFecha.type = "date";
  entradaFecha.id = "fecha-" + cliente.id;
  entradaFecha.value = cliente.fecha_vencimiento || "";

  const plazo = etiquetaDePlazo(cliente.fecha_vencimiento);

  // La espina: la franja de color del filo izquierdo de la tarjeta.
  // Lleva el mismo color que la etiqueta del plazo, para poder recorrer
  // la lista de arriba abajo viendo solo los filos.
  tarjeta.classList.add("espina-" + plazo.clase.replace("etiqueta-", ""));

  const etiqueta = document.createElement("span");
  etiqueta.className = "etiqueta " + plazo.clase;
  etiqueta.textContent = plazo.texto;
  if (cliente.fecha_vencimiento) {
    etiqueta.title = fechaEnPalabras(cliente.fecha_vencimiento);
  }

  // Al cambiar la fecha se guarda sola, sin botón de guardar.
  entradaFecha.addEventListener("change", function () {
    guardarFecha(cliente.id, entradaFecha.value);
  });

  bloqueFecha.appendChild(etiquetaCampo);
  bloqueFecha.appendChild(entradaFecha);
  bloqueFecha.appendChild(etiqueta);

  /* --- Eliminar --- */
  const acciones = document.createElement("div");
  acciones.className = "cliente-acciones";

  const enlaceDocumentos = document.createElement("a");
  enlaceDocumentos.className = "boton-texto";
  enlaceDocumentos.href = "/cliente?id=" + cliente.id;
  enlaceDocumentos.textContent = "Documentos";
  acciones.appendChild(enlaceDocumentos);

  const botonEliminar = document.createElement("button");
  botonEliminar.type = "button";
  botonEliminar.className = "boton-texto boton-texto-peligro";
  botonEliminar.textContent = "Eliminar";
  botonEliminar.addEventListener("click", function () {
    eliminarCliente(cliente);
  });

  acciones.appendChild(botonEliminar);

  tarjeta.appendChild(datos);
  tarjeta.appendChild(bloqueFecha);
  tarjeta.appendChild(acciones);
  return tarjeta;
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function cargarClientes() {
  try {
    const respuesta = await fetch("/api/clientes");
    if (!respuesta.ok) throw new Error();
    todosLosClientes = await respuesta.json();
    // Se dibuja pasando por el filtro para no perder lo que el contador
    // tuviera buscando o filtrado cuando cambió algo de la lista.
    filtrarYOrdenar();
  } catch (e) {
    contenedorLista.innerHTML =
      '<div class="vacio">No se pudo conectar con el servidor. ' +
      "Verifique que la aplicación esté encendida.</div>";
  }
}

async function agregarCliente(evento) {
  evento.preventDefault();
  ocultarAviso();

  const respuesta = await fetch("/api/clientes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nombre: campoNombre.value,
      dos_digitos: campoDigitos.value,
      fecha_vencimiento: campoFecha.value || null
    })
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }

  const cliente = await respuesta.json();
  mostrarAviso("Se agregó a " + cliente.nombre + ".", "exito");

  formulario.reset();
  campoNombre.focus();   // listo para escribir el siguiente
  cargarClientes();
}

async function guardarFecha(idCliente, fecha) {
  const respuesta = await fetch("/api/clientes/" + idCliente, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fecha_vencimiento: fecha || null })
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarClientes();   // se redibuja para actualizar la etiqueta de plazo
}

async function eliminarCliente(cliente) {
  const seguro = confirm(
    "¿Eliminar a " + cliente.nombre + "?\n\n" +
    "Se borran también todos sus documentos del computador. " +
    "Esta acción no se puede deshacer."
  );
  if (!seguro) return;

  const respuesta = await fetch("/api/clientes/" + cliente.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarClientes();
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

formulario.addEventListener("submit", agregarCliente);
cargarClientes();


/* ==========================================================
   Importar clientes desde un Excel o un CSV

   Son dos pasos, a propósito:
     1. Se manda el archivo y el servidor PROPONE una lista.
        Todavía no se guardó nada.
     2. El contador revisa y corrige en pantalla, y solo cuando
        aprieta "Crear" se guardan de verdad.
   ========================================================== */

const botonImportar = document.getElementById("boton-importar");
const campoImportar = document.getElementById("campo-importar");
const avisoImportar = document.getElementById("aviso-importar");
const revision = document.getElementById("revision");
const revisionResumen = document.getElementById("revision-resumen");
const revisionColumnas = document.getElementById("revision-columnas");
const revisionFilas = document.getElementById("revision-filas");
const botonConfirmar = document.getElementById("boton-confirmar");
const botonCancelar = document.getElementById("boton-cancelar");

/* Cómo se llama cada campo en pantalla. */
const NOMBRES_DE_CAMPO = {
  nombre: "Nombre",
  cedula: "Cédula",
  dos_digitos: "Dos dígitos",
  fecha_vencimiento: "Fecha de vencimiento"
};


function mostrarAvisoImportar(texto, tipo) { avisarEn(avisoImportar, texto, tipo); }
function ocultarAvisoImportar() { ocultarAvisoEn(avisoImportar); }

function cerrarRevision() {
  revision.className = "revision oculto";
  revisionFilas.innerHTML = "";
}


/* ----------------------------------------------------------
   Dibujar la tabla de revisión
   ---------------------------------------------------------- */

/* Crea una casilla de la tabla con un campo de texto adentro. */
function casillaEditable(valor, clase, maximo) {
  const casilla = document.createElement("td");
  const entrada = document.createElement("input");
  entrada.type = "text";
  entrada.value = valor || "";
  entrada.className = clase || "";
  if (maximo) entrada.maxLength = maximo;
  casilla.appendChild(entrada);
  return casilla;
}

function dibujarRevision(datos) {
  revisionFilas.innerHTML = "";

  const total = datos.propuestas.length;
  const marcados = datos.propuestas.filter(function (p) { return p.incluir; }).length;

  revisionResumen.textContent =
    "Se leyeron " + total + (total === 1 ? " fila" : " filas") + ". " +
    marcados + " están listas para crear. " +
    "Nada se ha guardado todavía: revise y corrija lo que haga falta.";

  /* --- Qué columnas se reconocieron y cuáles no --- */
  revisionColumnas.innerHTML = "";

  const reconocidas = Object.keys(datos.columnas_reconocidas)
    .map(function (campo) { return NOMBRES_DE_CAMPO[campo] || campo; });

  const linea = document.createElement("p");
  linea.style.margin = "0 0 4px";
  linea.textContent = "Columnas reconocidas: " + reconocidas.join(", ") + ".";
  revisionColumnas.appendChild(linea);

  // Aviso sobre el orden de las fechas, cuando el archivo no dejaba claro
  // si estaban escritas día/mes o mes/día.
  if (datos.aviso_fechas) {
    const alerta = document.createElement("p");
    alerta.className = "aviso aviso-fechas";
    alerta.textContent = datos.aviso_fechas;
    revisionColumnas.appendChild(alerta);
  }

  if (datos.columnas_ignoradas.length > 0) {
    const otra = document.createElement("p");
    otra.style.margin = "0 0 16px";
    otra.textContent =
      "El resto del archivo (" + datos.columnas_ignoradas.join(", ") +
      ") se guarda como notas del cliente.";
    revisionColumnas.appendChild(otra);
  }

  /* --- Una fila por cliente propuesto --- */
  datos.propuestas.forEach(function (propuesta) {
    const fila = document.createElement("tr");
    if (propuesta.avisos.length > 0) fila.className = "fila-revisar";

    /* Casilla de "crear sí o no" */
    const casillaMarca = document.createElement("td");
    const marca = document.createElement("input");
    marca.type = "checkbox";
    marca.checked = propuesta.incluir;
    marca.className = "marca-crear";
    casillaMarca.appendChild(marca);
    fila.appendChild(casillaMarca);

    /* Nombre, dígitos y fecha: todos editables aquí mismo */
    fila.appendChild(casillaEditable(propuesta.nombre, "campo-nombre", 120));
    fila.appendChild(casillaEditable(propuesta.dos_digitos, "campo-digitos", 2));

    const casillaFecha = document.createElement("td");
    const entradaFecha = document.createElement("input");
    entradaFecha.type = "date";
    entradaFecha.value = propuesta.fecha_vencimiento || "";
    entradaFecha.className = "campo-fecha";
    casillaFecha.appendChild(entradaFecha);
    fila.appendChild(casillaFecha);

    /* Avisos */
    const casillaAvisos = document.createElement("td");
    casillaAvisos.className = "casilla-avisos";
    casillaAvisos.textContent = propuesta.avisos.join(" · ");
    fila.appendChild(casillaAvisos);

    // Las notas no se muestran en la tabla para no volverla ilegible,
    // pero viajan con la fila y se guardan con el cliente.
    fila.dataset.notas = propuesta.notas || "";

    revisionFilas.appendChild(fila);
  });

  revision.className = "revision";
}


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function analizarArchivo(archivo) {
  ocultarAvisoImportar();
  cerrarRevision();
  mostrarAvisoImportar("Leyendo el archivo…", "exito");

  const formulario = new FormData();
  formulario.append("archivo", archivo, archivo.name);

  let respuesta;
  try {
    respuesta = await fetch("/api/importar/analizar", {
      method: "POST",
      body: formulario
    });
  } catch (e) {
    mostrarAvisoImportar("No se pudo conectar con el servidor.", "error");
    return;
  }

  if (!respuesta.ok) {
    mostrarAvisoImportar(await textoDelError(respuesta), "error");
    return;
  }

  ocultarAvisoImportar();
  dibujarRevision(await respuesta.json());
}

async function confirmarImportacion() {
  const seleccionados = [];

  Array.from(revisionFilas.children).forEach(function (fila) {
    if (!fila.querySelector(".marca-crear").checked) return;
    seleccionados.push({
      nombre: fila.querySelector(".campo-nombre").value,
      dos_digitos: fila.querySelector(".campo-digitos").value,
      fecha_vencimiento: fila.querySelector(".campo-fecha").value || null,
      notas: fila.dataset.notas || null
    });
  });

  if (seleccionados.length === 0) {
    mostrarAvisoImportar("No hay ninguna fila marcada para crear.", "error");
    return;
  }

  botonConfirmar.disabled = true;

  const respuesta = await fetch("/api/importar/confirmar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(seleccionados)
  });

  botonConfirmar.disabled = false;

  if (!respuesta.ok) {
    mostrarAvisoImportar(await textoDelError(respuesta), "error");
    return;
  }

  const resultado = await respuesta.json();

  let texto = resultado.creados === 1
    ? "Se creó 1 cliente."
    : "Se crearon " + resultado.creados + " clientes.";
  if (resultado.errores.length > 0) {
    texto += " " + resultado.errores.length + " fila(s) no se pudieron crear: " +
             resultado.errores.join(" | ");
  }

  mostrarAvisoImportar(texto, resultado.errores.length > 0 ? "error" : "exito");
  cerrarRevision();
  cargarClientes();
}


/* ----------------------------------------------------------
   Botones
   ---------------------------------------------------------- */

botonImportar.addEventListener("click", function () { campoImportar.click(); });

campoImportar.addEventListener("change", function () {
  if (campoImportar.files.length > 0) {
    analizarArchivo(campoImportar.files[0]);
  }
  campoImportar.value = "";   // permite volver a elegir el mismo archivo
});

botonConfirmar.addEventListener("click", confirmarImportacion);

botonCancelar.addEventListener("click", function () {
  cerrarRevision();
  ocultarAvisoImportar();
});


/* ----------------------------------------------------------
   Acciones sobre todos los clientes de una vez

   Después de importar 150 clientes de un Excel, dejarlos en el punto de
   partida uno por uno son 150 visitas. Estos dos botones lo hacen de un
   golpe, y los dos respetan lo que el contador ya haya puesto a mano.
   ---------------------------------------------------------- */

const avisoLote = document.getElementById("aviso-lote");
const botonListaBase = document.getElementById("boton-lista-base");
const botonVencimientos = document.getElementById("boton-vencimientos");

botonListaBase.addEventListener("click", async function () {
  const sinChecklist = todosLosClientes.filter(function (c) {
    return (c.checklist_total || 0) === 0;
  }).length;

  if (sinChecklist === 0) {
    avisarEn(avisoLote, "Todos los clientes ya tienen checklist.", "exito");
    return;
  }

  const seguro = confirm(
    "Se le va a poner la lista base del checklist a " +
    contar(sinChecklist, "cliente", "clientes") + ".\n\n" +
    "A los que ya tienen checklist no se les toca nada."
  );
  if (!seguro) return;

  this.disabled = true;
  try {
    const respuesta = await fetch("/api/clientes/lote/checklist-base", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    if (!respuesta.ok) {
      avisarEn(avisoLote, await textoDelError(respuesta), "error");
      return;
    }
    const r = await respuesta.json();
    avisarEn(avisoLote,
      "Listo: " + contar(r.puestos, "cliente quedó", "clientes quedaron") +
      " con la lista base de " + r.renglones + " renglones." +
      (r.saltados > 0
        ? " " + contar(r.saltados, "ya tenía", "ya tenían") + " checklist y no se tocaron."
        : ""),
      "exito");
    cargarClientes();
  } catch (e) {
    avisarEn(avisoLote, "No se pudo conectar con el servidor.", "error");
  } finally {
    this.disabled = false;
  }
});

botonVencimientos.addEventListener("click", async function () {
  const sinFecha = todosLosClientes.filter(function (c) {
    return !c.fecha_vencimiento;
  }).length;

  const seguro = confirm(
    "Se le va a poner la fecha del calendario oficial a " +
    contar(sinFecha, "cliente", "clientes") + " que no tiene fecha.\n\n" +
    "La fecha sale de la tabla del calendario que está cargada en el " +
    "programa, según los dos últimos dígitos de la cédula.\n\n" +
    "A los que ya tienen fecha no se les toca: esa la puso usted."
  );
  if (!seguro) return;

  this.disabled = true;
  try {
    const respuesta = await fetch("/api/clientes/lote/vencimientos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    if (!respuesta.ok) {
      avisarEn(avisoLote, await textoDelError(respuesta), "error");
      return;
    }
    const r = await respuesta.json();
    let texto = "Listo: " + contar(r.puestas, "fecha puesta", "fechas puestas") +
                " del calendario del año gravable " + r.anio + ".";
    if (r.respetadas > 0) {
      texto += " " + contar(r.respetadas, "cliente ya tenía", "clientes ya tenían") +
               " su fecha y no se tocaron.";
    }
    if (r.sin_fecha > 0) {
      texto += " " + contar(r.sin_fecha, "cliente no está", "clientes no están") +
               " en la tabla.";
    }
    avisarEn(avisoLote, texto, "exito");
    cargarClientes();
  } catch (e) {
    avisarEn(avisoLote, "No se pudo conectar con el servidor.", "error");
  } finally {
    this.disabled = false;
  }
});

/* El botón de vencimientos solo aparece si hay tabla cargada. Sin ella
   no haría nada, y un botón que no hace nada es peor que no tenerlo. */
(async function mirarSiHayTabla() {
  try {
    const respuesta = await fetch("/api/vencimientos");
    if (!respuesta.ok) return;
    const datos = await respuesta.json();
    if (datos.hay_tabla) {
      botonVencimientos.classList.remove("oculto");
      botonVencimientos.textContent =
        "Poner los vencimientos del calendario " + datos.anio;
    }
  } catch (e) {
    // Sin respuesta, el botón se queda escondido. No es crítico.
  }
})();
