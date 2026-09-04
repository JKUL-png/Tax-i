/* ==========================================================
   La pestaña Exógena

   Muestra lo que los terceros le reportaron a la DIAN sobre este
   cliente, y deja enlazar el soporte de cada cosa, decidir a qué
   renglón va cuando la DIAN propone varios, y llevar el valor al
   Formulario 210 uno por uno.

   Cómo están escritos los textos, que es lo que define el producto:

     "Sin soporte"  falta el papel. NUNCA "hay que declararlo".
     "Diferencia"   revíselo. NUNCA "está mal" ni "hay un error".
     La columna se llama "Renglón sugerido por la DIAN", no "sugerido"
     a secas: la sugerencia es de ella, no del programa.

   Y lo que el programa no hace: no elige entre los renglones que
   propone la DIAN, no une los posibles duplicados y no lleva nada al
   210 sin que el contador lo pida.
   ========================================================== */

(function () {
  "use strict";

  var idCliente = null;
  var datos = null;
  var renglones = [];
  var filtro = "";
  var busqueda = "";
  var orden = { columna: "", alReves: false };

  var ESTADOS = {
    coincide:          { texto: "Coincide", tono: "logro" },
    diferencia:        { texto: "Diferencia", tono: "revisar" },
    sin_soporte:       { texto: "Sin soporte", tono: "falta" },
    sin_comparar:      { texto: "Sin comparar", tono: "" },
    sin_reportar:      { texto: "Sin reportar", tono: "" },
    requiere_decision: { texto: "Requiere decisión", tono: "revisar" },
    posible_duplicado: { texto: "Posible duplicado", tono: "revisar" }
  };

  function $(id) { return document.getElementById(id); }

  function enPesos(numero) {
    if (numero === null || numero === undefined) return "—";
    return "$ " + Number(numero).toLocaleString("es-CO",
      { maximumFractionDigits: 2 });
  }

  /* ==========================================================
     Traer los datos
     ========================================================== */

  async function cargar() {
    if (!idCliente) return;
    try {
      const respuesta = await fetch("/api/clientes/" + idCliente + "/exogena");
      if (!respuesta.ok) return;
      datos = await respuesta.json();
    } catch (e) {
      return;
    }

    try {
      const r = await fetch("/api/clientes/" + idCliente + "/checklist");
      if (r.ok) renglones = await r.json();
    } catch (e) {
      renglones = [];
    }

    pintar();
  }

  /* ==========================================================
     Pintar
     ========================================================== */

  function pintar() {
    var vacia = $("exogena-vacia");
    var cargada = $("exogena-cargada");
    var conteo = $("exogena-conteo");
    if (!vacia || !cargada) return;

    if (!datos || !datos.hay_exogena) {
      vacia.classList.remove("oculto");
      cargada.classList.add("oculto");
      if (conteo) conteo.textContent = "";
      pintarAvisos([]);
      return;
    }

    vacia.classList.add("oculto");
    cargada.classList.remove("oculto");

    var carga = datos.carga;
    if (conteo) conteo.textContent = datos.filas.length;

    $("exogena-titulo").textContent =
      "Año gravable " + (carga.anio || "") + " · " + carga.nombre;

    /* La fecha de corte se muestra siempre, porque el primer aviso de la
       DIAN dice que la información puede cambiar si un tercero la
       modifica después de esa fecha. */
    $("exogena-corte").textContent =
      "Información al corte del " + fechaEnPalabras(carga.fecha_corte) +
      ". Archivo: " + (carga.archivo || "—") + ".";

    pintarAvisos(carga.avisos || []);
    pintarTopes(datos.topes || []);
    pintarFiltros();
    pintarFilas();
  }

  function pintarAvisos(avisos) {
    var caja = $("exogena-avisos");
    if (!caja) return;
    caja.innerHTML = "";
    if (!avisos.length) {
      caja.classList.add("oculto");
      return;
    }
    caja.classList.remove("oculto");

    var titulo = document.createElement("p");
    titulo.className = "exogena-avisos-titulo";
    titulo.textContent = "Lo que advierte la DIAN";
    caja.appendChild(titulo);

    /* Textuales. No se resumen ni se reescriben: son de la DIAN. */
    avisos.forEach(function (aviso) {
      var parrafo = document.createElement("p");
      parrafo.className = "exogena-aviso";
      parrafo.textContent = aviso;
      caja.appendChild(parrafo);
    });
  }

  function pintarTopes(topes) {
    var caja = $("exogena-topes");
    caja.innerHTML = "";
    if (!topes.length) return;

    var titulo = document.createElement("h3");
    titulo.className = "exogena-topes-titulo";
    titulo.textContent = "Topes";
    caja.appendChild(titulo);

    var fila = document.createElement("div");
    fila.className = "exogena-topes-fila";
    topes.forEach(function (tope) {
      var tarjeta = document.createElement("div");
      tarjeta.className = "exogena-tope";
      var nombre = document.createElement("span");
      nombre.className = "exogena-tope-nombre";
      nombre.textContent = tope.etiqueta || ("Tope " + tope.numero);
      var monto = document.createElement("strong");
      monto.className = "exogena-tope-valor";
      monto.textContent = enPesos(tope.valor);
      tarjeta.appendChild(nombre);
      tarjeta.appendChild(monto);
      fila.appendChild(tarjeta);
    });
    caja.appendChild(fila);
  }

  function pintarFiltros() {
    var caja = $("exogena-filtros");
    caja.innerHTML = "";

    var todos = document.createElement("button");
    todos.type = "button";
    todos.className = "exogena-filtro" + (filtro ? "" : " exogena-filtro-activo");
    todos.textContent = "Todos (" + datos.filas.length + ")";
    todos.addEventListener("click", function () { filtro = ""; pintarFiltros(); pintarFilas(); });
    caja.appendChild(todos);

    Object.keys(ESTADOS).forEach(function (clave) {
      var cuantos = datos.conteos[clave] || 0;
      if (!cuantos) return;
      var boton = document.createElement("button");
      boton.type = "button";
      boton.className = "exogena-filtro estado-" + (ESTADOS[clave].tono || "gris")
                        + (filtro === clave ? " exogena-filtro-activo" : "");
      boton.textContent = ESTADOS[clave].texto + " (" + cuantos + ")";
      boton.addEventListener("click", function () {
        filtro = (filtro === clave) ? "" : clave;
        pintarFiltros();
        pintarFilas();
      });
      caja.appendChild(boton);
    });
  }

  /* Deja un texto listo para comparar: sin tildes, en minúscula y sin
     los puntos de miles. Lo último es lo que permite escribir
     «2342990» y encontrar «$ 2.342.990», que es como uno se acuerda de
     una cifra cuando la está buscando. */
  function paraBuscar(texto) {
    return (texto === null || texto === undefined ? "" : String(texto))
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function soloDigitos(texto) {
    return String(texto === null || texto === undefined ? "" : texto)
      .replace(/[^0-9]/g, "");
  }

  /* Todo lo que una fila permite buscar, en un solo texto.

     Va el «Uso declaración Sugerida» completo porque ahí está el
     renglón: buscando «R32» aparecen todas las filas que la DIAN mandó
     a ese renglón, que es la pregunta que uno se hace de verdad. */
  function textoDeLaFila(fila) {
    return paraBuscar([
      fila.detalle, fila.nombre_reporta, fila.nit_reporta, fila.concepto,
      fila.uso_sugerido, fila.estado_texto, fila.nombre_original,
      fila.renglon_elegido
    ].join(" "));
  }

  function coincideConLaBusqueda(fila, aguja) {
    if (textoDeLaFila(fila).indexOf(aguja) !== -1) return true;
    /* Y por la cifra, escrita como sea: con puntos o sin ellos. */
    var digitos = soloDigitos(aguja);
    if (digitos.length >= 3) {
      if (soloDigitos(fila.valor).indexOf(digitos) !== -1) return true;
      if (soloDigitos(fila.nit_reporta).indexOf(digitos) !== -1) return true;
    }
    return false;
  }

  function filasAMostrar() {
    var lista = datos.filas.slice();

    if (filtro === "sin_reportar") lista = [];
    else if (filtro) {
      lista = lista.filter(function (f) {
        return f.marcas.indexOf(filtro) !== -1;
      });
    }

    var aguja = paraBuscar(busqueda).trim();
    if (aguja) {
      lista = lista.filter(function (f) {
        return coincideConLaBusqueda(f, aguja);
      });
    }

    if (orden.columna) {
      lista.sort(function (a, b) {
        var x, y;
        if (orden.columna === "valor") { x = a.valor || 0; y = b.valor || 0; }
        else if (orden.columna === "estado") { x = a.estado_texto; y = b.estado_texto; }
        else { x = a.detalle; y = b.detalle; }
        if (x < y) return orden.alReves ? 1 : -1;
        if (x > y) return orden.alReves ? -1 : 1;
        return 0;
      });
    }
    return lista;
  }

  function pintarFilas() {
    var cuerpo = $("exogena-filas");
    cuerpo.innerHTML = "";

    var lista = filasAMostrar();

    lista.forEach(function (fila) {
      cuerpo.appendChild(filaDeTabla(fila));
    });

    /* Los renglones del contador que la exógena no menciona. No
       significa que falte nada: significa que ningún tercero reportó
       algo que la DIAN haya mandado allí. */
    var sueltos = datos.sin_reportar || [];
    var aguja = paraBuscar(busqueda).trim();
    if (aguja) {
      sueltos = sueltos.filter(function (renglon) {
        return paraBuscar(renglon.titulo || "").indexOf(aguja) !== -1;
      });
    }
    if ((!filtro || filtro === "sin_reportar") && sueltos.length) {
      sueltos.forEach(function (renglon) {
        cuerpo.appendChild(filaSinReportar(renglon));
      });
    }

    if (!cuerpo.children.length) {
      var fila = document.createElement("tr");
      var celda = document.createElement("td");
      celda.colSpan = 5;
      celda.className = "vacio";
      celda.textContent = busqueda.trim()
        ? "Ningún registro dice «" + busqueda.trim() + "»."
        : "Ningún registro con ese estado.";
      fila.appendChild(celda);
      cuerpo.appendChild(fila);
    }

    var total = datos.filas.length + (datos.sin_reportar || []).length;
    $("exogena-pie").textContent =
      "Mostrando " + cuerpo.children.length + " de " + total + " renglones.";

    var cuantos = $("exogena-buscar-cuantos");
    if (cuantos) {
      cuantos.textContent = busqueda.trim()
        ? cuerpo.children.length + " de " + total
        : "";
    }
  }

  function etiquetaDeEstado(clave) {
    var info = ESTADOS[clave] || { texto: clave, tono: "" };
    var marca = document.createElement("span");
    marca.className = "exogena-estado estado-" + (info.tono || "gris");
    marca.textContent = info.texto;
    return marca;
  }

  function filaDeTabla(fila) {
    var tr = document.createElement("tr");
    tr.className = "exogena-fila estado-fila-" + fila.estado;

    /* --- Concepto y quién reporta --- */
    var td1 = document.createElement("td");
    var detalle = document.createElement("div");
    detalle.className = "exogena-detalle";
    detalle.textContent = fila.detalle;
    td1.appendChild(detalle);

    var quien = document.createElement("div");
    quien.className = "exogena-quien";
    quien.textContent = fila.nombre_reporta + " · NIT " + fila.nit_reporta;
    if (fila.concepto) quien.textContent += " · concepto " + fila.concepto;
    td1.appendChild(quien);

    if (Object.keys(fila.adicional || {}).length) {
      var mas = document.createElement("details");
      mas.className = "exogena-adicional";
      var resumen = document.createElement("summary");
      resumen.textContent = "Información adicional";
      mas.appendChild(resumen);
      var lista = document.createElement("dl");
      Object.keys(fila.adicional).forEach(function (clave) {
        var dt = document.createElement("dt");
        dt.textContent = clave;
        var dd = document.createElement("dd");
        dd.textContent = fila.adicional[clave];
        lista.appendChild(dt);
        lista.appendChild(dd);
      });
      mas.appendChild(lista);
      td1.appendChild(mas);
    }
    tr.appendChild(td1);

    /* --- Reporta la DIAN --- */
    var td2 = document.createElement("td");
    td2.className = "numero";
    var monto = document.createElement("strong");
    monto.textContent = enPesos(fila.valor);
    td2.appendChild(monto);

    if (fila.estado === "diferencia" && fila.cifra_soporte) {
      /* Las dos cifras, la de la DIAN y la del soporte. Sin decir cuál
         está bien: eso lo mira él. */
      var otra = document.createElement("div");
      otra.className = "exogena-otra-cifra";
      otra.textContent = "el soporte dice " + enPesos(fila.cifra_soporte.valor);
      td2.appendChild(otra);
    }
    tr.appendChild(td2);

    /* --- Soporte cargado --- */
    tr.appendChild(celdaDeSoporte(fila));

    /* --- Renglón sugerido por la DIAN --- */
    tr.appendChild(celdaDeRenglon(fila));

    /* --- Estado --- */
    var td5 = document.createElement("td");
    fila.marcas.forEach(function (marca) {
      td5.appendChild(etiquetaDeEstado(marca));
    });

    if (fila.posible_duplicado && fila.duplicado_de.length) {
      /* Por qué se marcó. Es lo que le permite descartarlo de un
         vistazo cuando no lo es. Marcar no es decidir: las dos filas
         siguen ahí, enteras. */
      var porque = document.createElement("p");
      porque.className = "exogena-porque";
      porque.textContent = fila.duplicado_de[0].motivo;
      td5.appendChild(porque);
    }
    tr.appendChild(td5);

    return tr;
  }

  function celdaDeSoporte(fila) {
    var td = document.createElement("td");

    if (fila.nombre_original) {
      var enlace = document.createElement("a");
      enlace.className = "exogena-soporte";
      enlace.href = "/api/documentos/" + fila.documento_id + "/archivo";
      enlace.target = "_blank";
      enlace.rel = "noopener";
      enlace.textContent = fila.nombre_original;
      enlace.title = "Abrir el documento original";
      td.appendChild(enlace);

      var quitar = document.createElement("button");
      quitar.type = "button";
      quitar.className = "boton-texto";
      quitar.textContent = "Quitar";
      quitar.addEventListener("click", function () {
        enlazarSoporte(fila.id, null);
      });
      td.appendChild(quitar);
      return td;
    }

    var falta = document.createElement("span");
    falta.className = "exogena-falta";
    falta.textContent = "Falta el soporte";
    td.appendChild(falta);

    if (fila.sugerencia) {
      /* Sugerencia por el NIT del tercero, hecha con código. La
         confirma él. */
      var propuesta = document.createElement("button");
      propuesta.type = "button";
      propuesta.className = "sugerencia";
      propuesta.textContent = "¿Es «" + fila.sugerencia.nombre + "»?";
      propuesta.title = "Coincide el NIT del tercero. Confirme usted.";
      propuesta.addEventListener("click", function () {
        enlazarSoporte(fila.id, fila.sugerencia.id);
      });
      td.appendChild(propuesta);
    }
    return td;
  }

  function celdaDeRenglon(fila) {
    var td = document.createElement("td");

    /* El texto de la DIAN va completo, palabra por palabra. No se
       recorta ni se reescribe. */
    var texto = document.createElement("p");
    texto.className = "exogena-uso";
    texto.textContent = fila.uso_sugerido || "La DIAN no sugiere renglón.";
    td.appendChild(texto);

    if (fila.nota) {
      var nota = document.createElement("p");
      nota.className = "exogena-nota";
      nota.textContent = fila.nota;
      td.appendChild(nota);
    }

    if (fila.requiere_decision) {
      td.appendChild(cajaDeDecision(fila));
    } else if (fila.renglon) {
      td.appendChild(botonAl210(fila));
    }
    return td;
  }

  function cajaDeDecision(fila) {
    var caja = document.createElement("div");
    caja.className = "exogena-decision";

    var pregunta = document.createElement("p");
    pregunta.className = "exogena-decision-titulo";
    pregunta.textContent = fila.renglon_elegido
      ? "Usted eligió:"
      : "La DIAN propone más de un renglón. Elija cuál corresponde:";
    caja.appendChild(pregunta);

    /* Las opciones se muestran tal como la DIAN las escribió. El
       programa no elige: ni con IA, ni con reglas, ni mirando el signo
       del valor. Es criterio profesional. */
    fila.renglones.forEach(function (renglon) {
      var opcion = document.createElement("button");
      opcion.type = "button";
      opcion.className = "exogena-opcion"
        + (fila.renglon_elegido === renglon.codigo ? " exogena-opcion-elegida" : "");
      opcion.textContent = renglon.texto;
      opcion.addEventListener("click", function () {
        elegirRenglon(fila.id,
          fila.renglon_elegido === renglon.codigo ? "" : renglon.codigo);
      });
      caja.appendChild(opcion);
    });

    if (fila.renglon_elegido) caja.appendChild(botonAl210(fila));
    return caja;
  }

  function botonAl210(fila) {
    var boton = document.createElement("button");
    boton.type = "button";
    boton.className = "boton-texto exogena-al-210";
    boton.textContent = "Llevar al Formulario 210 →";
    boton.addEventListener("click", function () { llevarAl210(fila); });
    return boton;
  }

  function filaSinReportar(renglon) {
    var tr = document.createElement("tr");
    tr.className = "exogena-fila estado-fila-sin_reportar";

    var td1 = document.createElement("td");
    var titulo = document.createElement("div");
    titulo.className = "exogena-detalle";
    titulo.textContent = renglon.titulo;
    td1.appendChild(titulo);
    var quien = document.createElement("div");
    quien.className = "exogena-quien";
    quien.textContent = renglon.origen === "dian"
      ? "Renglón de la DIAN, sin registros este año"
      : "Renglón suyo";
    td1.appendChild(quien);
    tr.appendChild(td1);

    var td2 = document.createElement("td");
    td2.className = "numero";
    td2.textContent = "—";
    tr.appendChild(td2);

    var td3 = document.createElement("td");
    td3.textContent = renglon.documentos
      ? contar(renglon.documentos, "documento", "documentos")
      : "Falta el soporte";
    tr.appendChild(td3);

    var td4 = document.createElement("td");
    var nada = document.createElement("p");
    nada.className = "exogena-uso";
    nada.textContent = "Ningún tercero reportó algo para este renglón.";
    td4.appendChild(nada);
    tr.appendChild(td4);

    var td5 = document.createElement("td");
    td5.appendChild(etiquetaDeEstado("sin_reportar"));
    tr.appendChild(td5);
    return tr;
  }

  /* ==========================================================
     Las acciones
     ========================================================== */

  async function enlazarSoporte(idFila, idDocumento) {
    try {
      const respuesta = await fetch("/api/exogena/filas/" + idFila + "/soporte", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ documento_id: idDocumento })
      });
      if (!respuesta.ok) {
        const error = await respuesta.json();
        avisarEn($("aviso-exogena"), error.detalle || "No se pudo enlazar.", "error");
        return;
      }
      await cargar();
    } catch (e) {
      avisarEn($("aviso-exogena"), "No se pudo enlazar el soporte.", "error");
    }
  }

  async function elegirRenglon(idFila, codigo) {
    try {
      const respuesta = await fetch("/api/exogena/filas/" + idFila + "/renglon", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ codigo: codigo })
      });
      if (!respuesta.ok) {
        const error = await respuesta.json();
        avisarEn($("aviso-exogena"), error.detalle || "No se pudo guardar.", "error");
        return;
      }
      await cargar();
    } catch (e) {
      avisarEn($("aviso-exogena"), "No se pudo guardar la decisión.", "error");
    }
  }

  /* Llevar un valor al 210. Uno por uno y con aprobación explícita:
     nunca en lote, nunca automático.

     La casilla la propone el programa cuando puede saberla, y eso NO
     contradice la regla de no decidir: el renglón ya está decidido —lo
     decidió la DIAN en la exógena, o lo eligió él— y lo que falta es en
     cuál fila de SU hoja de trabajo va. Eso se resuelve leyendo la
     etiqueta de la fila, no interpretando la ley.

     Cuando de verdad hay que escoger, se abre un selector con el nombre
     de cada fila. Nunca más una lista numerada en un cuadro del
     navegador. */
  async function llevarAl210(fila) {
    let datos;
    try {
      const respuesta = await fetch("/api/exogena/filas/" + fila.id + "/casillas");
      datos = await respuesta.json();
      if (!respuesta.ok) {
        avisarEn($("aviso-exogena"), datos.detalle
                 || "No se pudo consultar la plantilla.", "error");
        return;
      }
    } catch (e) {
      avisarEn($("aviso-exogena"), "No se pudo consultar la plantilla.", "error");
      return;
    }

    const casillas = datos.casillas || [];
    if (!casillas.length) {
      avisarEn($("aviso-exogena"),
        "La plantilla no tiene ninguna casilla conectada para ese renglón."
        + " Puede que ese renglón sea de los que la plantilla calcula sola.",
        "error");
      return;
    }

    if (datos.recomendada) {
      confirmarYEscribir(fila, datos.recomendada, datos.motivo, casillas);
    } else {
      abrirElegirCasilla(fila, casillas, "");
    }
  }

  function confirmarYEscribir(fila, casilla, motivo, casillas) {
    const seguro = window.confirm(
      "¿Escribir " + enPesos(fila.valor) + " en la casilla "
      + casilla.celda + " del Formulario 210?\n\n"
      + (casilla.descripcion || "") + "\n"
      + (motivo ? "\n" + motivo + "\n" : "")
      + "\n" + fila.detalle
      + "\nReportado por " + fila.nombre_reporta + "."
      + "\n\nQueda anotado en el historial y lo puede cambiar después."
      + "\n\n(Cancele si prefiere escoger otra casilla.)");
    if (seguro) {
      escribirEn(fila, casilla.celda);
    } else if (casillas && casillas.length > 1) {
      abrirElegirCasilla(fila, casillas, casilla.celda);
    }
  }

  /* El selector de casilla. Es el mismo campo con búsqueda de los
     renglones, que ya sabe buscar escribiendo, moverse con las flechas
     y cerrarse con Escape. */
  function abrirElegirCasilla(fila, casillas, puesta) {
    const fondo = document.createElement("div");
    fondo.className = "elegir-casilla-fondo";

    const caja = document.createElement("div");
    caja.className = "elegir-casilla";

    const titulo = document.createElement("h3");
    titulo.textContent = "¿En cuál casilla va " + enPesos(fila.valor) + "?";
    caja.appendChild(titulo);

    const ayuda = document.createElement("p");
    ayuda.className = "ayuda";
    ayuda.textContent = fila.detalle + " — reportado por "
                      + fila.nombre_reporta + ". Estas son las casillas de"
                      + " ese renglón que la plantilla sí lee.";
    caja.appendChild(ayuda);

    let escogida = puesta || "";
    const selector = SelectorRenglon.crear({
      renglones: casillas.map(function (c) {
        return { id: c.celda, titulo: c.celda + " — " + (c.descripcion || "") };
      }),
      elegido: escogida || null,
      vacio: "— escoja la casilla —",
      etiqueta: "Casilla del Formulario 210",
      alElegir: function (id) { escogida = id; }
    });
    caja.appendChild(selector.elemento);

    const acciones = document.createElement("div");
    acciones.className = "elegir-casilla-acciones";

    const cancelar = document.createElement("button");
    cancelar.type = "button";
    cancelar.className = "boton-texto";
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", cerrar);

    const anotar = document.createElement("button");
    anotar.type = "button";
    anotar.className = "boton";
    anotar.textContent = "Anotar";
    anotar.addEventListener("click", function () {
      if (!escogida) {
        ayuda.textContent = "Escoja una casilla primero.";
        return;
      }
      cerrar();
      escribirEn(fila, escogida);
    });

    acciones.appendChild(cancelar);
    acciones.appendChild(anotar);
    caja.appendChild(acciones);
    fondo.appendChild(caja);
    document.body.appendChild(fondo);

    function cerrar() {
      document.removeEventListener("keydown", conEscape);
      fondo.remove();
    }
    function conEscape(evento) {
      if (evento.key === "Escape") cerrar();
    }
    document.addEventListener("keydown", conEscape);
    fondo.addEventListener("click", function (evento) {
      if (evento.target === fondo) cerrar();
    });
  }

  async function escribirEn(fila, celda) {
    try {
      const respuesta = await fetch("/api/exogena/filas/" + fila.id + "/al-210", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ celda: celda })
      });
      const cuerpo = await respuesta.json();
      if (!respuesta.ok) {
        avisarEn($("aviso-exogena"), cuerpo.detalle || "No se pudo escribir.",
                 "error");
        return;
      }
      avisarEn($("aviso-exogena"),
        "Listo: " + enPesos(fila.valor) + " quedó en " + celda + ".",
        "exito");
    } catch (e) {
      avisarEn($("aviso-exogena"), "No se pudo escribir el valor.", "error");
    }
  }

  async function subirArchivo(archivo) {
    var caja = $("aviso-exogena");
    avisarEn(caja, "Leyendo el archivo…", "");

    var cuerpo = new FormData();
    cuerpo.append("archivo", archivo);

    try {
      const respuesta = await fetch("/api/clientes/" + idCliente + "/exogena", {
        method: "POST",
        body: cuerpo
      });
      const datosNuevos = await respuesta.json();
      if (!respuesta.ok) {
        avisarEn(caja, datosNuevos.detalle || "No se pudo leer el archivo.",
                 "error");
        return;
      }

      var r = datosNuevos.renglones;
      var mensaje = "Se leyeron " + datosNuevos.resumen.registros
                    + " registros. Se crearon " + r.creados + " renglones";
      if (r.ya_estaban) mensaje += " y ya estaban " + r.ya_estaban;
      mensaje += ".";
      if (r.huerfanos.length) {
        mensaje += " Ojo: " + r.huerfanos.length + " renglón(es) de la carga"
                 + " anterior ya no aparecen en este archivo. No se borraron;"
                 + " si sobran, quítelos usted desde el checklist.";
      }
      avisarEn(caja, mensaje, "exito");
      await cargar();

      /* Cargar la exógena crea renglones, así que el checklist y los
         documentos que estaban pintados quedaron viejos: el selector de
         cada documento se arma con esos renglones. Sin esto, el
         contador tiene que recargar la página a mano para que los
         renglones nuevos le aparezcan. */
      if (typeof cargarChecklist === "function") {
        await cargarChecklist();
        if (typeof cargarDocumentos === "function") await cargarDocumentos();
      }
    } catch (e) {
      avisarEn(caja, "No se pudo cargar el archivo.", "error");
    }
  }

  async function quitarExogena() {
    if (!datos || !datos.carga) return;
    var anio = datos.carga.anio;
    var confirmado = window.confirm(
      "¿Quitar la exógena del año " + anio + " de este cliente?\n\n"
      + "Se quitan los " + datos.filas.length + " registros reportados."
      + "\nLos renglones del checklist NO se tocan: pueden tener documentos"
      + " asignados.");
    if (!confirmado) return;

    try {
      await fetch("/api/clientes/" + idCliente + "/exogena/" + anio,
                  { method: "DELETE" });
      await cargar();
    } catch (e) {
      avisarEn($("aviso-exogena"), "No se pudo quitar.", "error");
    }
  }

  /* ==========================================================
     Encender
     ========================================================== */

  function encender(id) {
    idCliente = id;

    var campo = $("campo-exogena");
    ["boton-cargar-exogena", "boton-recargar-exogena"].forEach(function (cual) {
      var boton = $(cual);
      if (boton && campo) {
        boton.addEventListener("click", function () { campo.click(); });
      }
    });
    if (campo) {
      campo.addEventListener("change", function () {
        if (campo.files && campo.files[0]) subirArchivo(campo.files[0]);
        campo.value = "";
      });
    }

    var quitar = $("boton-quitar-exogena");
    if (quitar) quitar.addEventListener("click", quitarExogena);

    /* Buscar dentro de la tabla. Se filtra mientras escribe, sin botón:
       con treinta y seis registros ya cansa el scroll, y una exógena de
       verdad trae muchos más. */
    var buscar = $("exogena-buscar");
    if (buscar) {
      buscar.addEventListener("input", function () {
        busqueda = buscar.value;
        pintarFilas();
      });
      /* Escape limpia, que es lo que uno intenta sin pensarlo. */
      buscar.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape" && buscar.value) {
          buscar.value = "";
          busqueda = "";
          pintarFilas();
        }
      });
    }

    document.querySelectorAll(".exogena-tabla th.ordenable")
      .forEach(function (encabezado) {
        encabezado.addEventListener("click", function () {
          var columna = encabezado.dataset.orden;
          orden.alReves = (orden.columna === columna) ? !orden.alReves : false;
          orden.columna = columna;
          pintarFilas();
        });
      });

    cargar();
  }

  window.ExogenaTaxi = { encender: encender, recargar: cargar };
})();
