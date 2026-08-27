/* ==========================================================
   Pantalla de un cliente: subir y ver sus documentos.

   El id del cliente viene en la dirección: /cliente?id=3

   JavaScript plano, sin librerías.
   ========================================================== */

const idCliente = new URLSearchParams(window.location.search).get("id");

const tituloNombre = document.getElementById("nombre-cliente");
const lineaDatos = document.getElementById("datos-cliente");
const zonaArrastre = document.getElementById("zona-arrastre");
const campoArchivos = document.getElementById("campo-archivos");
const campoCarpeta = document.getElementById("campo-carpeta");
const botonArchivos = document.getElementById("boton-archivos");
const botonCarpeta = document.getElementById("boton-carpeta");
const contenedorLista = document.getElementById("lista-documentos");
const conteo = document.getElementById("conteo");
const progreso = document.getElementById("progreso");
const progresoTexto = document.getElementById("progreso-texto");
const informe = document.getElementById("informe");
const aviso = document.getElementById("aviso");

/* De a cuántos archivos se manda cada tanda. Se parte en tandas para que
   subir 200 fotos no sea una sola petición gigante que se pueda caer. */
const ARCHIVOS_POR_TANDA = 20;
const PESO_POR_TANDA = 40 * 1024 * 1024;   // 40 MB


/* ----------------------------------------------------------
   Avisos
   ---------------------------------------------------------- */

let temporizadorAviso = null;

function mostrarAviso(texto, tipo) {
  aviso.textContent = texto;
  aviso.className = "aviso aviso-" + tipo;
  clearTimeout(temporizadorAviso);
  if (tipo === "exito") {
    temporizadorAviso = setTimeout(ocultarAviso, 4000);
  }
}

function ocultarAviso() {
  aviso.className = "aviso oculto";
  aviso.textContent = "";
}


/* ----------------------------------------------------------
   Formatos
   ---------------------------------------------------------- */

/* 1536000 -> "1,5 MB" */
function pesoEnPalabras(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
}

/* "2026-08-26T14:03:00" -> "26/08/2026, 2:03 p. m." */
function fechaHoraEnPalabras(texto) {
  const fecha = new Date(texto);
  if (isNaN(fecha)) return texto;
  return fecha.toLocaleString("es-CO", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "numeric", minute: "2-digit"
  });
}


/* ----------------------------------------------------------
   Dibujar
   ---------------------------------------------------------- */

function dibujarDocumentos(documentos) {
  contenedorLista.innerHTML = "";
  conteo.textContent = documentos.length > 0 ? "(" + documentos.length + ")" : "";

  if (documentos.length === 0) {
    const vacio = document.createElement("div");
    vacio.className = "vacio";
    vacio.textContent =
      "Todavía no hay documentos de este cliente. Suba los primeros arriba.";
    contenedorLista.appendChild(vacio);
    return;
  }

  documentos.forEach(function (documento) {
    contenedorLista.appendChild(dibujarDocumento(documento));
  });
}

function dibujarDocumento(documento) {
  const tarjeta = document.createElement("article");
  tarjeta.className = "documento";

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

  /* --- Acciones --- */
  const acciones = document.createElement("div");
  acciones.className = "documento-acciones";

  const enlaceAbrir = document.createElement("a");
  enlaceAbrir.className = "boton-texto";
  enlaceAbrir.href = "/api/documentos/" + documento.id + "/archivo";
  enlaceAbrir.target = "_blank";
  enlaceAbrir.rel = "noopener";
  enlaceAbrir.textContent = "Abrir";

  const botonEliminar = document.createElement("button");
  botonEliminar.type = "button";
  botonEliminar.className = "boton-texto boton-texto-peligro";
  botonEliminar.textContent = "Eliminar";
  botonEliminar.addEventListener("click", function () {
    eliminarDocumento(documento);
  });

  acciones.appendChild(enlaceAbrir);
  acciones.appendChild(botonEliminar);

  tarjeta.appendChild(tipo);
  tarjeta.appendChild(datos);
  tarjeta.appendChild(acciones);
  return tarjeta;
}

/* Muestra el resumen de lo que se subió y lo que quedó por fuera. */
function mostrarInforme(guardados, ignorados) {
  informe.innerHTML = "";

  if (guardados === 0 && ignorados.length === 0) {
    informe.className = "informe oculto";
    return;
  }

  const resumen = document.createElement("p");
  resumen.className = "informe-resumen";
  if (guardados === 1) {
    resumen.textContent = "Se guardó 1 documento.";
  } else {
    resumen.textContent = "Se guardaron " + guardados + " documentos.";
  }
  informe.appendChild(resumen);

  if (ignorados.length > 0) {
    const titulo = document.createElement("p");
    titulo.className = "informe-titulo";
    titulo.textContent = ignorados.length === 1
      ? "1 archivo quedó por fuera:"
      : ignorados.length + " archivos quedaron por fuera:";
    informe.appendChild(titulo);

    const lista = document.createElement("ul");
    lista.className = "informe-lista";
    ignorados.forEach(function (motivo) {
      const renglon = document.createElement("li");
      renglon.textContent = motivo;
      lista.appendChild(renglon);
    });
    informe.appendChild(lista);
  }

  informe.className = "informe";
}


/* ----------------------------------------------------------
   Arrastrar y soltar
   ---------------------------------------------------------- */

/* Recorre una entrada del arrastre. Si es carpeta, entra y saca todo
   lo que hay adentro, incluidas las subcarpetas. */
function recorrerEntrada(entrada, acumulador) {
  return new Promise(function (terminar) {
    if (entrada.isFile) {
      entrada.file(
        function (archivo) { acumulador.push(archivo); terminar(); },
        function () { terminar(); }
      );
      return;
    }

    if (entrada.isDirectory) {
      const lector = entrada.createReader();
      // readEntries devuelve máximo 100 de una vez: hay que volver a
      // preguntar hasta que conteste con una lista vacía.
      const leerTanda = function () {
        lector.readEntries(
          function (entradas) {
            if (entradas.length === 0) { terminar(); return; }
            const pendientes = entradas.map(function (hija) {
              return recorrerEntrada(hija, acumulador);
            });
            Promise.all(pendientes).then(leerTanda);
          },
          function () { terminar(); }
        );
      };
      leerTanda();
      return;
    }

    terminar();
  });
}

/* Saca la lista de archivos de lo que se soltó en la zona. */
async function archivosDelArrastre(transferencia) {
  const entradas = [];

  // Ojo: webkitGetAsEntry hay que llamarlo de una, antes de cualquier
  // espera, porque el navegador vacía la lista apenas termina el evento.
  if (transferencia.items) {
    for (let i = 0; i < transferencia.items.length; i++) {
      const item = transferencia.items[i];
      if (item.kind !== "file") continue;
      const entrada = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
      if (entrada) entradas.push(entrada);
    }
  }

  // Navegador que no soporta carpetas: al menos los archivos sueltos.
  if (entradas.length === 0) {
    return Array.from(transferencia.files || []);
  }

  const acumulador = [];
  for (const entrada of entradas) {
    await recorrerEntrada(entrada, acumulador);
  }
  return acumulador;
}

zonaArrastre.addEventListener("dragover", function (evento) {
  evento.preventDefault();
  zonaArrastre.classList.add("zona-activa");
});

zonaArrastre.addEventListener("dragleave", function (evento) {
  // Solo se apaga cuando el puntero sale de verdad de la zona, no cuando
  // pasa por encima de un hijo.
  if (!zonaArrastre.contains(evento.relatedTarget)) {
    zonaArrastre.classList.remove("zona-activa");
  }
});

zonaArrastre.addEventListener("drop", async function (evento) {
  evento.preventDefault();
  zonaArrastre.classList.remove("zona-activa");
  const archivos = await archivosDelArrastre(evento.dataTransfer);
  subirArchivos(archivos);
});

// Si se sueltan archivos fuera de la zona, el navegador los abriría en
// una pestaña y se perdería la página. Esto lo evita.
window.addEventListener("dragover", function (e) { e.preventDefault(); });
window.addEventListener("drop", function (e) { e.preventDefault(); });

botonArchivos.addEventListener("click", function () { campoArchivos.click(); });
botonCarpeta.addEventListener("click", function () { campoCarpeta.click(); });

campoArchivos.addEventListener("change", function () {
  subirArchivos(Array.from(campoArchivos.files));
  campoArchivos.value = "";   // permite volver a elegir el mismo archivo
});

campoCarpeta.addEventListener("change", function () {
  subirArchivos(Array.from(campoCarpeta.files));
  campoCarpeta.value = "";
});


/* ----------------------------------------------------------
   Conversación con el servidor
   ---------------------------------------------------------- */

async function textoDelError(respuesta) {
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo.detail === "string") return cuerpo.detail;
    if (Array.isArray(cuerpo.detail) && cuerpo.detail.length > 0) {
      return cuerpo.detail[0].msg.replace("Value error, ", "");
    }
  } catch (e) {
    // Si no era JSON se usa el mensaje de abajo.
  }
  return "No se pudo completar la operación.";
}

async function cargarCliente() {
  try {
    const respuesta = await fetch("/api/clientes/" + idCliente);
    if (!respuesta.ok) throw new Error();
    const cliente = await respuesta.json();
    tituloNombre.textContent = cliente.nombre;
    document.title = cliente.nombre + " · Asistente de renta";

    let texto = "Cédula termina en " + cliente.dos_digitos;
    if (cliente.fecha_vencimiento) {
      texto += " · vence el " + cliente.fecha_vencimiento;
    } else {
      texto += " · sin fecha de vencimiento";
    }
    lineaDatos.textContent = texto;
  } catch (e) {
    tituloNombre.textContent = "No se encontró el cliente";
    lineaDatos.textContent = "";
  }
}

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

/* Parte la lista en tandas para no mandar todo en una sola petición. */
function armarTandas(archivos) {
  const tandas = [];
  let tanda = [];
  let peso = 0;

  archivos.forEach(function (archivo) {
    if (tanda.length > 0 &&
        (tanda.length >= ARCHIVOS_POR_TANDA || peso + archivo.size > PESO_POR_TANDA)) {
      tandas.push(tanda);
      tanda = [];
      peso = 0;
    }
    tanda.push(archivo);
    peso += archivo.size;
  });

  if (tanda.length > 0) tandas.push(tanda);
  return tandas;
}

let subiendo = false;

async function subirArchivos(archivos) {
  if (subiendo) {
    mostrarAviso("Espere a que termine la subida anterior.", "error");
    return;
  }
  if (!archivos || archivos.length === 0) return;

  ocultarAviso();
  informe.className = "informe oculto";
  subiendo = true;
  progreso.className = "progreso";

  const tandas = armarTandas(archivos);
  let guardados = 0;
  let ignorados = [];
  let enviados = 0;

  try {
    for (const tanda of tandas) {
      progresoTexto.textContent =
        "Subiendo " + (enviados + 1) + " de " + archivos.length + "…";

      const formulario = new FormData();
      tanda.forEach(function (archivo) {
        // El tercer argumento es el nombre: si el archivo vino de una
        // carpeta, se manda la ruta relativa para no perder el contexto.
        formulario.append("archivos", archivo,
                          archivo.webkitRelativePath || archivo.name);
      });

      const respuesta = await fetch("/api/clientes/" + idCliente + "/documentos", {
        method: "POST",
        body: formulario
      });

      if (!respuesta.ok) {
        mostrarAviso(await textoDelError(respuesta), "error");
        break;
      }

      const resultado = await respuesta.json();
      guardados += resultado.guardados.length;
      ignorados = ignorados.concat(resultado.ignorados);
      enviados += tanda.length;
    }
  } catch (e) {
    mostrarAviso("Se perdió la conexión con el servidor durante la subida.", "error");
  }

  subiendo = false;
  progreso.className = "progreso oculto";
  mostrarInforme(guardados, ignorados);
  cargarDocumentos();
}

async function eliminarDocumento(documento) {
  const seguro = confirm(
    "¿Eliminar \"" + documento.nombre_original + "\"?\n\n" +
    "Se borra el archivo del computador y no se puede deshacer."
  );
  if (!seguro) return;

  const respuesta = await fetch("/api/documentos/" + documento.id, {
    method: "DELETE"
  });

  if (!respuesta.ok) {
    mostrarAviso(await textoDelError(respuesta), "error");
    return;
  }
  cargarDocumentos();
}


/* ----------------------------------------------------------
   Arranque
   ---------------------------------------------------------- */

if (!idCliente) {
  tituloNombre.textContent = "Falta el cliente";
  lineaDatos.textContent = "Vuelva a la lista y entre a un cliente.";
} else {
  cargarCliente();
  cargarDocumentos();
}
