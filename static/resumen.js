/* ==========================================================
   Resumen del cliente, en una hoja lista para imprimir.

   Se imprime con el propio navegador (Control+P, o Command+P en Mac)
   y desde ahí se puede guardar como PDF. No hace falta ninguna
   librería ni ningún programa extra.
   ========================================================== */

const idCliente = new URLSearchParams(window.location.search).get("id");
const contenido = document.getElementById("contenido");
const volver = document.getElementById("volver");

document.getElementById("boton-imprimir").addEventListener("click", function () {
  window.print();
});


/* Crea un elemento con texto adentro. Se usa textContent y no innerHTML
   para que un nombre de archivo raro se muestre como texto y ya. */
function elemento(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto !== undefined) nodo.textContent = texto;
  return nodo;
}

/* Dibuja una lista de documentos con su casilla marcada o vacía. */
function listaDeRenglones(titulos, recibidos) {
  if (titulos.length === 0) {
    return elemento("p", "resumen-vacio",
      recibidos ? "Ninguno todavía." : "Nada pendiente.");
  }

  const lista = elemento("ul", "resumen-lista");
  titulos.forEach(function (titulo) {
    const renglon = elemento("li", recibidos ? "renglon-si" : "renglon-no");
    renglon.appendChild(elemento("span", "casilla", recibidos ? "☑" : "☐"));
    renglon.appendChild(elemento("span", null, titulo));
    lista.appendChild(renglon);
  });
  return lista;
}


function dibujar(resumen) {
  const cliente = resumen.cliente;
  const lista = resumen.checklist;
  contenido.innerHTML = "";

  document.title = "Resumen · " + cliente.nombre;

  /* --- Encabezado --- */
  contenido.appendChild(elemento("h1", "resumen-titulo", "Resumen de documentos"));
  contenido.appendChild(elemento("h2", "resumen-cliente", cliente.nombre));

  const datos = elemento("p", "resumen-datos");
  datos.textContent = "Cédula termina en " + cliente.dos_digitos;
  contenido.appendChild(datos);

  if (cliente.fecha_vencimiento_texto) {
    const fecha = elemento("p", "resumen-datos");
    fecha.textContent =
      "Fecha de vencimiento: " + cliente.fecha_vencimiento_texto;
    contenido.appendChild(fecha);

    // La fecha se muestra como referencia, no como un dato que el
    // programa haya calculado. Es editable en la pantalla del cliente.
    contenido.appendChild(elemento("p", "resumen-referencia",
      "Referencia tomada del calendario oficial — verificable y editable."));
  } else {
    contenido.appendChild(elemento("p", "resumen-datos",
      "Fecha de vencimiento: sin registrar"));
  }

  if (cliente.notas) {
    contenido.appendChild(elemento("h3", "resumen-seccion", "Datos adicionales"));
    const notas = elemento("p", "resumen-notas", cliente.notas);
    contenido.appendChild(notas);
  }

  /* --- El estado del checklist, en grande --- */
  const faltan = lista.faltantes.length;
  const marcador = elemento("div", "resumen-marcador");
  marcador.appendChild(elemento("span", "marcador-numero",
    lista.recibidos.length + " de " + lista.total));
  marcador.appendChild(elemento("span", "marcador-texto",
    faltan === 0
      ? "documentos recibidos · completo"
      : "documentos recibidos · faltan " + faltan));
  if (faltan > 0) marcador.classList.add("marcador-pendiente");
  contenido.appendChild(marcador);

  /* --- Lo que falta va primero: es lo que importa --- */
  contenido.appendChild(elemento("h3", "resumen-seccion",
    "Faltan (" + faltan + ")"));
  contenido.appendChild(listaDeRenglones(lista.faltantes, false));

  contenido.appendChild(elemento("h3", "resumen-seccion",
    "Recibidos (" + lista.recibidos.length + ")"));
  contenido.appendChild(listaDeRenglones(lista.recibidos, true));

  /* --- Los archivos guardados --- */
  contenido.appendChild(elemento("h3", "resumen-seccion",
    "Archivos guardados (" + resumen.documentos.length + ")"));

  if (resumen.documentos.length === 0) {
    contenido.appendChild(elemento("p", "resumen-vacio", "Ninguno todavía."));
  } else {
    const tabla = elemento("table", "tabla-archivos");
    const cuerpo = document.createElement("tbody");

    resumen.documentos.forEach(function (documento) {
      const fila = document.createElement("tr");
      fila.appendChild(elemento("td", "columna-tipo", documento.tipo));
      fila.appendChild(elemento("td", null, documento.nombre));

      let detalle = documento.peso + " · " + documento.fecha;
      if (documento.venia_en_zip) {
        detalle += " · venía en " + documento.venia_en_zip;
      }
      fila.appendChild(elemento("td", "columna-detalle", detalle));
      cuerpo.appendChild(fila);
    });

    tabla.appendChild(cuerpo);
    contenido.appendChild(tabla);
  }

  /* --- Pie --- */
  const pie = elemento("div", "resumen-pie");
  pie.appendChild(elemento("p", null, "Generado el " + resumen.generado_en + "."));
  pie.appendChild(elemento("p", null, resumen.nota_legal));
  contenido.appendChild(pie);
}


async function cargar() {
  if (!idCliente) {
    contenido.innerHTML = "<p>Falta indicar el cliente.</p>";
    return;
  }

  volver.href = "/cliente?id=" + idCliente;

  try {
    const respuesta = await fetch("/api/clientes/" + idCliente + "/resumen");
    if (!respuesta.ok) throw new Error();
    dibujar(await respuesta.json());
  } catch (e) {
    contenido.innerHTML = "<p>No se pudo cargar el resumen del cliente.</p>";
  }
}

cargar();
