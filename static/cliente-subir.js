/* ==========================================================
   Subir documentos, en dos pasos.

   Antes los archivos que se arrastraban entraban derecho al expediente
   del cliente. Ahora caen primero en una ZONA DE REVISIÓN: se ven, se
   pueden marcar y quitar, y solo entran de verdad cuando el contador le
   da a "Confirmar carga".

   Por qué: arrastrar es un gesto fácil de equivocar. Se suelta la
   carpeta que no era, o se suelta encima del cliente equivocado, y
   antes eso ya era irreversible. Ahora hay un momento para mirar.

   Es el mismo patrón que la importación de clientes desde Excel:
   analizar, mostrar, confirmar. Nada se guarda hasta el último paso.
   ========================================================== */

const zonaArrastre = document.getElementById("zona-arrastre");
const campoArchivos = document.getElementById("campo-archivos");
const campoCarpeta = document.getElementById("campo-carpeta");
const botonArchivos = document.getElementById("boton-archivos");
const botonCarpeta = document.getElementById("boton-carpeta");
const progreso = document.getElementById("progreso");
const progresoTexto = document.getElementById("progreso-texto");
const informe = document.getElementById("informe");

const cajaRevision = document.getElementById("revision-carga");
const listaRevision = document.getElementById("revision-lista");
const conteoRevision = document.getElementById("revision-conteo");
const casillaTodosRev = document.getElementById("revision-todos");
const rotuloSeleccionRev = document.getElementById("revision-seleccion");
const botonQuitarMarcados = document.getElementById("revision-quitar-marcados");
const botonQuitarTodos = document.getElementById("revision-quitar-todos");
const botonConfirmarCarga = document.getElementById("revision-confirmar");
const resumenPeso = document.getElementById("revision-resumen-peso");
const cajaDescartados = document.getElementById("revision-descartados");

/* Cuánto se manda en cada petición. Un correo de temporada puede traer
   cien archivos; mandarlos todos de un golpe agota la memoria y se cae
   a la mitad sin decir cuántos alcanzaron a entrar. */
const ARCHIVOS_POR_TANDA = 20;
const PESO_POR_TANDA = 40 * 1024 * 1024;   // 40 MB

/* Los mismos límites que aplica el servidor (ver app/documentos.py).
   Se comprueban también aquí para poder avisar en la zona de revisión,
   antes de mandar nada, en vez de que el archivo viaje para nada. */
const PESO_MAXIMO = 25 * 1024 * 1024;        // 25 MB por archivo
const PESO_MAXIMO_ZIP = 100 * 1024 * 1024;   // 100 MB si es un ZIP

const EXTENSIONES_QUE_ENTRAN = [
  ".pdf", ".xml", ".zip",
  ".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif",
  ".xlsx", ".csv"
];


/* ----------------------------------------------------------
   La zona de revisión

   `porSubir` son los archivos que están esperando. Cada uno lleva un
   número propio (`clave`) porque dos archivos pueden llamarse igual si
   vienen de carpetas distintas, y hay que poder quitar uno sin quitar
   el otro.
   ---------------------------------------------------------- */

let porSubir = [];
let marcadosRevision = new Set();
let siguienteClave = 1;

/* Basura del sistema que no es un documento. La misma lista que el
   servidor ignora en silencio (ver app/documentos.py). */
function esBasura(nombre) {
  const corto = nombre.replace(/\\/g, "/").split("/").pop();
  return corto === ".DS_Store" ||
         corto.startsWith("._") ||
         nombre.includes("__MACOSX/");
}

function extensionDe(nombre) {
  const punto = nombre.lastIndexOf(".");
  return punto === -1 ? "" : nombre.slice(punto).toLowerCase();
}

/* Revisa un archivo antes de ponerlo en la lista. Devuelve el motivo
   por el que no entra, o null si está bien. */
function porQueNoEntra(archivo, nombre) {
  const extension = extensionDe(nombre);

  if (!EXTENSIONES_QUE_ENTRAN.includes(extension)) {
    return "tipo de archivo no admitido";
  }
  if (archivo.size === 0) {
    return "el archivo está vacío";
  }
  if (extension === ".zip") {
    if (archivo.size > PESO_MAXIMO_ZIP) return "el ZIP pesa más de 100 MB";
  } else if (archivo.size > PESO_MAXIMO) {
    return "pesa más de 25 MB";
  }
  return null;
}

/* Mete archivos en la zona de revisión. No sube nada. */
function ponerEnRevision(archivos) {
  if (!archivos || archivos.length === 0) return;

  const descartados = [];
  let repetidos = 0;

  archivos.forEach(function (archivo) {
    const nombre = archivo.webkitRelativePath || archivo.name;

    // La basura del sistema se salta sin avisar: no es un documento y
    // llenar la lista de .DS_Store solo estorba.
    if (esBasura(nombre)) return;

    const motivo = porQueNoEntra(archivo, nombre);
    if (motivo) {
      descartados.push(nombre + " — " + motivo + ".");
      return;
    }

    // ¿Ya estaba esperando? Se compara nombre y tamaño: es lo que se
    // puede saber sin leer el archivo. Los duplicados de verdad, por
    // contenido, los detecta el servidor al confirmar.
    const yaEstaba = porSubir.some(function (uno) {
      return uno.nombre === nombre && uno.archivo.size === archivo.size;
    });
    if (yaEstaba) { repetidos += 1; return; }

    porSubir.push({ clave: siguienteClave++, nombre: nombre, archivo: archivo });
  });

  if (repetidos > 0) {
    descartados.push(
      contar(repetidos, "archivo ya estaba", "archivos ya estaban") +
      " en la lista de abajo."
    );
  }

  mostrarDescartados(descartados);
  dibujarRevision();
}

function mostrarDescartados(motivos) {
  cajaDescartados.innerHTML = "";
  if (motivos.length === 0) {
    cajaDescartados.className = "revision-descartados oculto";
    return;
  }

  const titulo = document.createElement("p");
  titulo.className = "informe-titulo";
  titulo.textContent = motivos.length === 1
    ? "1 archivo no se puede subir:"
    : motivos.length + " archivos no se pueden subir:";
  cajaDescartados.appendChild(titulo);

  const lista = document.createElement("ul");
  lista.className = "informe-lista";
  motivos.forEach(function (motivo) {
    const renglon = document.createElement("li");
    renglon.textContent = motivo;
    lista.appendChild(renglon);
  });
  cajaDescartados.appendChild(lista);
  cajaDescartados.className = "revision-descartados";
}

function dibujarRevision() {
  listaRevision.innerHTML = "";

  if (porSubir.length === 0) {
    cajaRevision.className = "revision-carga oculto";
    marcadosRevision = new Set();
    return;
  }

  cajaRevision.className = "revision-carga";
  conteoRevision.textContent = "(" + porSubir.length + ")";

  porSubir.forEach(function (uno) {
    const renglon = document.createElement("li");
    renglon.className = "revision-renglon";

    const casilla = document.createElement("input");
    casilla.type = "checkbox";
    casilla.className = "documento-casilla";
    casilla.checked = marcadosRevision.has(uno.clave);
    casilla.setAttribute("aria-label", "Marcar " + uno.nombre);
    casilla.addEventListener("change", function () {
      if (casilla.checked) {
        marcadosRevision.add(uno.clave);
      } else {
        marcadosRevision.delete(uno.clave);
      }
      renglon.classList.toggle("documento-marcado", casilla.checked);
      refrescarSeleccionRevision();
    });
    renglon.classList.toggle("documento-marcado", casilla.checked);

    const datos = document.createElement("div");
    datos.className = "revision-datos";

    const nombre = document.createElement("p");
    nombre.className = "documento-nombre";
    // textContent y no innerHTML: el nombre lo puso el cliente, no yo.
    nombre.textContent = uno.nombre;

    const peso = document.createElement("p");
    peso.className = "documento-detalle";
    peso.textContent = pesoEnPalabras(uno.archivo.size);
    if (extensionDe(uno.nombre) === ".zip") {
      peso.textContent += " · se abre y se guarda lo que trae adentro";
    }

    datos.appendChild(nombre);
    datos.appendChild(peso);

    const quitar = document.createElement("button");
    quitar.type = "button";
    quitar.className = "boton-texto boton-texto-peligro";
    quitar.textContent = "Quitar";
    quitar.addEventListener("click", function () {
      porSubir = porSubir.filter(function (otro) {
        return otro.clave !== uno.clave;
      });
      marcadosRevision.delete(uno.clave);
      dibujarRevision();
    });

    renglon.appendChild(casilla);
    renglon.appendChild(datos);
    renglon.appendChild(quitar);
    listaRevision.appendChild(renglon);
  });

  const peso = porSubir.reduce(function (suma, uno) {
    return suma + uno.archivo.size;
  }, 0);
  resumenPeso.textContent =
    contar(porSubir.length, "archivo", "archivos") + " · " + pesoEnPalabras(peso);

  refrescarSeleccionRevision();
}

function refrescarSeleccionRevision() {
  const cuantos = marcadosRevision.size;
  const total = porSubir.length;

  rotuloSeleccionRev.textContent = cuantos === 0
    ? "Marcar todos"
    : contar(cuantos, "marcado", "marcados");

  botonQuitarMarcados.disabled = cuantos === 0;
  casillaTodosRev.checked = total > 0 && cuantos === total;
  casillaTodosRev.indeterminate = cuantos > 0 && cuantos < total;
}

casillaTodosRev.addEventListener("change", function () {
  marcadosRevision = casillaTodosRev.checked
    ? new Set(porSubir.map(function (uno) { return uno.clave; }))
    : new Set();
  dibujarRevision();
});

botonQuitarMarcados.addEventListener("click", function () {
  // Quitar de la zona de revisión no borra nada: estos archivos nunca
  // llegaron a entrar. Por eso no pregunta.
  porSubir = porSubir.filter(function (uno) {
    return !marcadosRevision.has(uno.clave);
  });
  marcadosRevision = new Set();
  dibujarRevision();
});

botonQuitarTodos.addEventListener("click", function () {
  porSubir = [];
  marcadosRevision = new Set();
  mostrarDescartados([]);
  dibujarRevision();
});

botonConfirmarCarga.addEventListener("click", function () {
  subirArchivos(porSubir.map(function (uno) { return uno; }));
});


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
  // A revisar, no a subir.
  ponerEnRevision(archivos);
});

// Si se sueltan archivos fuera de la zona, el navegador los abriría en
// una pestaña y se perdería la página. Esto lo evita.
window.addEventListener("dragover", function (e) { e.preventDefault(); });
window.addEventListener("drop", function (e) { e.preventDefault(); });

botonArchivos.addEventListener("click", function () { campoArchivos.click(); });
botonCarpeta.addEventListener("click", function () { campoCarpeta.click(); });

campoArchivos.addEventListener("change", function () {
  ponerEnRevision(Array.from(campoArchivos.files));
  campoArchivos.value = "";   // permite volver a elegir el mismo archivo
});

campoCarpeta.addEventListener("change", function () {
  ponerEnRevision(Array.from(campoCarpeta.files));
  campoCarpeta.value = "";
});


/* ----------------------------------------------------------
   Confirmar la carga: aquí sí se sube
   ---------------------------------------------------------- */

/* Parte la lista en tandas para no mandar todo en una sola petición. */
function armarTandas(pendientes) {
  const tandas = [];
  let tanda = [];
  let peso = 0;

  pendientes.forEach(function (uno) {
    if (tanda.length > 0 &&
        (tanda.length >= ARCHIVOS_POR_TANDA ||
         peso + uno.archivo.size > PESO_POR_TANDA)) {
      tandas.push(tanda);
      tanda = [];
      peso = 0;
    }
    tanda.push(uno);
    peso += uno.archivo.size;
  });

  if (tanda.length > 0) tandas.push(tanda);
  return tandas;
}

let subiendo = false;

async function subirArchivos(pendientes) {
  if (subiendo) {
    mostrarAviso("Espere a que termine la subida anterior.", "error");
    return;
  }
  if (!pendientes || pendientes.length === 0) return;

  ocultarAviso();
  informe.className = "informe oculto";
  subiendo = true;
  botonConfirmarCarga.disabled = true;
  progreso.className = "progreso";

  const tandas = armarTandas(pendientes);
  let guardados = 0;
  let ignorados = [];
  let enviados = 0;
  let entraronTodas = true;

  // El indicador dice exactamente en qué documento va y cuántos segundos
  // lleva. Vive en comun.js.
  const reloj = relojDeProgreso(progresoTexto);

  try {
    for (const tanda of tandas) {
      // Los documentos van en tandas, así que se nombra el tramo entero:
      // "Subiendo los documentos 6 a 10 de 12". Cuando la tanda es de uno
      // solo, se dice su nombre, que es más útil que el número.
      const primero = enviados + 1;
      const ultimo = enviados + tanda.length;
      reloj.paso(
        tanda.length === 1
          ? "Subiendo " + primero + " de " + pendientes.length
            + ": " + tanda[0].nombre + "…"
          : "Subiendo los documentos " + primero + " a " + ultimo
            + " de " + pendientes.length + "…"
      );

      const formulario = new FormData();
      tanda.forEach(function (uno) {
        // El tercer argumento es el nombre: si el archivo vino de una
        // carpeta, se manda la ruta relativa para no perder el contexto.
        formulario.append("archivos", uno.archivo, uno.nombre);
      });

      const respuesta = await fetch("/api/clientes/" + idCliente + "/documentos", {
        method: "POST",
        body: formulario
      });

      if (!respuesta.ok) {
        mostrarAviso(await textoDelError(respuesta), "error");
        entraronTodas = false;
        break;
      }

      const resultado = await respuesta.json();
      guardados += resultado.guardados.length;
      ignorados = ignorados.concat(resultado.ignorados);
      enviados += tanda.length;

      // Lo que ya entró sale de la zona de revisión. Si la siguiente
      // tanda falla, en la zona queda EXACTAMENTE lo que no se subió,
      // listo para reintentarlo sin duplicar lo que sí entró.
      const entregados = new Set(tanda.map(function (uno) { return uno.clave; }));
      porSubir = porSubir.filter(function (uno) {
        return !entregados.has(uno.clave);
      });
      marcadosRevision = new Set();
    }
  } catch (e) {
    mostrarAviso("Se perdió la conexión con el servidor durante la subida.", "error");
    entraronTodas = false;
  }

  reloj.detener();
  subiendo = false;
  botonConfirmarCarga.disabled = false;
  progreso.className = "progreso oculto";

  if (entraronTodas) mostrarDescartados([]);
  dibujarRevision();
  mostrarInforme(guardados, ignorados);

  cargarDocumentos();
  cargarHistorial();
  refrescarMensaje();
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
