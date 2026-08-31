/* ==========================================================
   El riel y las tres vistas del cliente

   Dos cosas, las dos de la pantalla del cliente:

   1. EL RIEL. La lista de clientes pegada a la izquierda, agrupada por
      urgencia. Antes, cambiar de cliente era volver a la lista y entrar
      al siguiente: en temporada eso son cientos de idas y vueltas.

      Los grupos van en el orden en que importan, y responden a una sola
      pregunta: ¿a quién le tengo que trabajar ahora?

         Vencidos        se pasó la fecha y todavía le falta algo
         Esta semana     vence dentro de 7 días y le falta algo
         Pendientes      le falta algo, con la fecha más lejos o sin fecha
         Al día          no le falta nada

      Un cliente al que no le falta nada no es urgente aunque venza
      mañana: ya está listo para presentar. Por eso lo que manda es lo
      que falta, y la fecha ordena adentro de cada grupo.

   2. LAS TRES VISTAS. Documentos, Formulario 210, Historial y exportar.
      Antes eran siete secciones plegables una debajo de otra: para
      llegar al 210 había que bajar toda la pantalla y volver a subir
      para ver qué faltaba.

   Este archivo no calcula nada del negocio: pide la lista al servidor y
   la dibuja. Las fechas las interpreta diasQueFaltan(), de comun.js, que
   es la misma que usa el resto del programa.
   ========================================================== */

(function () {
  "use strict";

  var lista = document.getElementById("riel-lista");
  var buscador = document.getElementById("riel-buscar");
  if (!lista) return;

  var idActual = Number(new URLSearchParams(location.search).get("id")) || 0;
  var clientes = [];

  /* ----------------------------------------------------------
     En cuál parada se está

     El riel lleva a tres sitios: agregar clientes, un cliente, y la
     cuenta. Cuál está seleccionado se calcula AQUÍ, mirando la
     dirección, y no se escribe a mano en cada archivo HTML: cuando se
     agregó la pantalla de /clientes, la clase escrita a mano en el HTML
     de inicio se quedó marcando la parada equivocada.
     ---------------------------------------------------------- */

  (function marcarParada() {
    var camino = location.pathname.replace(/\/+$/, "") || "/";

    var agregar = document.querySelector(".riel-agregar");
    if (agregar && camino === "/clientes") {
      agregar.classList.add("riel-agregar-actual");
      agregar.setAttribute("aria-current", "page");
    }

    var cuenta = document.querySelector(".riel-pie a");
    if (cuenta && camino === "/cuenta") {
      cuenta.classList.add("riel-pie-actual");
      cuenta.setAttribute("aria-current", "page");
    }

    /* La marca de arriba lleva al inicio, así que cuando se está en el
       inicio no hay a dónde ir: se marca y ya. */
    var marca = document.querySelector(".riel-marca");
    if (marca && camino === "/") {
      marca.setAttribute("aria-current", "page");
    }
  })();

  /* ----------------------------------------------------------
     Los grupos
     ---------------------------------------------------------- */

  var GRUPOS = [
    { llave: "vencidos",  titulo: "Vencidos",    clase: "riel-grupo-vencidos" },
    { llave: "semana",    titulo: "Esta semana", clase: "riel-grupo-semana" },
    { llave: "pendiente", titulo: "Pendientes",  clase: "riel-grupo-pendiente" },
    { llave: "aldia",     titulo: "Al día",      clase: "riel-grupo-aldia" }
  ];

  function faltantesDe(cliente) {
    var total = cliente.checklist_total || 0;
    var recibidos = cliente.checklist_recibidos || 0;
    return Math.max(0, total - recibidos);
  }

  /* diasQueFaltan(), en comun.js, da por hecho que hay fecha: hace
     texto.split() de una. Un cliente sin fecha de vencimiento es normal
     —la fecha se escribe a mano— así que aquí se filtra antes. */
  function diasODesconocido(fecha) {
    if (!fecha) return null;
    return diasQueFaltan(fecha);
  }

  function grupoDe(cliente) {
    /* Sin checklist todavía no se sabe qué le falta, así que va con los
       pendientes: hay algo que hacer ahí, que es armarle la lista. */
    if ((cliente.checklist_total || 0) === 0) return "pendiente";
    if (faltantesDe(cliente) === 0) return "aldia";

    var dias = diasODesconocido(cliente.fecha_vencimiento);
    if (dias === null) return "pendiente";
    if (dias < 0) return "vencidos";
    if (dias <= 7) return "semana";
    return "pendiente";
  }

  /* Dentro de cada grupo: primero el que vence antes. Los que no tienen
     fecha van al final, porque no se puede decir que urjan. */
  function porFecha(a, b) {
    var da = diasODesconocido(a.fecha_vencimiento);
    var db = diasODesconocido(b.fecha_vencimiento);
    if (da === null && db === null) return a.nombre.localeCompare(b.nombre, "es");
    if (da === null) return 1;
    if (db === null) return -1;
    if (da !== db) return da - db;
    return a.nombre.localeCompare(b.nombre, "es");
  }

  /* ----------------------------------------------------------
     Dibujar
     ---------------------------------------------------------- */

  function dibujar() {
    var texto = (buscador ? buscador.value : "").trim().toLowerCase();

    var visibles = clientes.filter(function (c) {
      if (!texto) return true;
      return c.nombre.toLowerCase().indexOf(texto) !== -1 ||
             String(c.dos_digitos || "").indexOf(texto) !== -1;
    });

    lista.textContent = "";

    if (visibles.length === 0) {
      var vacio = document.createElement("p");
      vacio.className = "riel-vacio";
      vacio.textContent = texto
        ? "Ningún cliente coincide con “" + texto + "”."
        : "Todavía no hay clientes. Agregue el primero con el botón de arriba.";
      lista.appendChild(vacio);
      return;
    }

    GRUPOS.forEach(function (grupo) {
      var suyos = visibles.filter(function (c) { return grupoDe(c) === grupo.llave; });
      if (suyos.length === 0) return;
      suyos.sort(porFecha);

      var caja = document.createElement("div");
      caja.className = "riel-grupo " + grupo.clase;

      var titulo = document.createElement("p");
      titulo.className = "riel-grupo-titulo";
      titulo.appendChild(document.createTextNode(grupo.titulo));
      var cuantos = document.createElement("span");
      cuantos.className = "cuantos";
      cuantos.textContent = suyos.length;
      titulo.appendChild(cuantos);
      caja.appendChild(titulo);

      suyos.forEach(function (cliente) {
        caja.appendChild(dibujarFila(cliente, grupo.llave));
      });

      lista.appendChild(caja);
    });

    /* Si el cliente que se está viendo quedó fuera de la parte visible
       del riel, se lo trae. Pasa cuando la lista es larga. */
    var actual = lista.querySelector(".riel-fila-actual");
    if (actual && actual.scrollIntoView) {
      actual.scrollIntoView({ block: "nearest" });
    }
  }

  function dibujarFila(cliente, llaveGrupo) {
    var fila = document.createElement("a");
    fila.className = "riel-fila";
    fila.href = "/cliente?id=" + cliente.id;
    if (cliente.id === idActual) {
      fila.classList.add("riel-fila-actual");
      fila.setAttribute("aria-current", "page");
    }

    var nombre = document.createElement("span");
    nombre.className = "riel-fila-nombre";
    nombre.textContent = cliente.nombre;
    /* El nombre completo al pasar el mouse: en 244px los nombres largos
       se cortan, y un contador tiene clientes con cuatro apellidos. */
    nombre.title = cliente.nombre;
    fila.appendChild(nombre);

    var faltan = faltantesDe(cliente);
    if (llaveGrupo === "aldia") {
      var listo = document.createElement("span");
      listo.className = "riel-fila-listo";
      listo.textContent = "completo";
      fila.appendChild(listo);
    } else if ((cliente.checklist_total || 0) === 0) {
      var sinLista = document.createElement("span");
      sinLista.className = "riel-fila-listo";
      sinLista.textContent = "sin lista";
      fila.appendChild(sinLista);
    } else {
      var cuenta = document.createElement("span");
      cuenta.className = "riel-fila-faltan";
      cuenta.textContent = faltan;
      cuenta.title = faltan === 1
        ? "Falta 1 documento"
        : "Faltan " + faltan + " documentos";
      fila.appendChild(cuenta);
    }

    return fila;
  }

  async function cargar() {
    try {
      var respuesta = await fetch("/api/clientes");
      if (!respuesta.ok) throw new Error("no se pudo leer la lista");
      clientes = await respuesta.json();
      dibujar();
    } catch (error) {
      lista.textContent = "";
      var aviso = document.createElement("p");
      aviso.className = "riel-vacio";
      aviso.textContent = "No se pudo cargar la lista de clientes. " +
                          "Revise que el programa siga prendido.";
      lista.appendChild(aviso);
    }
  }

  if (buscador) {
    buscador.addEventListener("input", dibujar);
  }

  /* Se deja una manija afuera para que la pantalla de agregar clientes
     pueda pedir que el riel se vuelva a cargar. Sin esto, agregar o
     eliminar un cliente dejaba el riel mostrando lo de antes hasta que
     alguien recargara la página a mano. */
  window.RielTaxi = { recargar: cargar };

  /* ==========================================================
     Las tres vistas
     ========================================================== */

  var botones = Array.prototype.slice.call(
    document.querySelectorAll(".area-vista-boton"));
  var LLAVE_VISTA = "taxi-vista-cliente";

  /* Las vistas son solo de la pantalla del cliente. En la de agregar y en
     la de la cuenta no hay pestañas, y sin esta salida mostrar() se
     llamaba a sí misma sin parar buscando una que no existe. */
  if (botones.length === 0) {
    cargar();
    return;
  }

  /* Las vistas que ya se abrieron alguna vez en esta carga de la página. */
  var abiertas = {};

  function mostrar(cual, recordar) {
    var hayAlguna = false;

    botones.forEach(function (boton) {
      var suya = boton.dataset.vista === cual;
      if (suya) hayAlguna = true;
      boton.classList.toggle("area-vista-actual", suya);
      boton.setAttribute("aria-selected", suya ? "true" : "false");
      var panel = document.getElementById("vista-" + boton.dataset.vista);
      if (!panel) return;
      panel.hidden = !suya;

      /* La primera vez que se entra a una vista, se despliegan sus
         secciones. Antes de las pestañas tenía sentido que el Formulario
         210 llegara plegado: estaba en la misma pantalla que todo lo
         demás y desplegado era un scroll interminable. Ahora tiene su
         propia pestaña, y llegar a una pestaña vacía con un triangulito
         para abrir es hacer trabajar dos veces por lo mismo.

         Solo la primera vez: si después el contador la pliega, se queda
         como él la dejó. */
      if (suya && !abiertas[cual]) {
        abiertas[cual] = true;
        panel.querySelectorAll("details.plegable").forEach(function (seccion) {
          seccion.open = true;
        });
      }
    });

    if (!hayAlguna) return mostrar("documentos", recordar);

    if (recordar) {
      try {
        window.localStorage.setItem(LLAVE_VISTA, cual);
      } catch (e) {
        /* Sin almacenamiento simplemente no se recuerda. No es grave. */
      }
    }
  }

  /* Los botones del perfil del cliente necesitan poder saltar a otra
     pestaña: "Generar el mensaje para el cliente" vive en la pestaña de
     Historial, no en la de Documentos. Sin esta manija, esos botones
     abrían una sección que estaba dentro de un panel escondido y no
     pasaba absolutamente nada al apretarlos. */
  window.RielTaxi.mostrarVista = function (cual) { mostrar(cual, true); };

  botones.forEach(function (boton) {
    boton.addEventListener("click", function () {
      mostrar(boton.dataset.vista, true);
      /* Al cambiar de vista se sube: la vista nueva empieza arriba, no
         a la altura a la que quedó la anterior. */
      window.scrollTo({ top: 0, behavior: "instant" });
    });
  });

  /* Cuál vista se abre al entrar. Manda la dirección (#formulario) por
     encima de lo recordado: si alguien manda ese enlace, tiene que
     llegar a lo que dice. */
  var pedida = (location.hash || "").replace("#", "");
  var recordada = "documentos";
  try {
    recordada = window.localStorage.getItem(LLAVE_VISTA) || "documentos";
  } catch (e) { /* sin almacenamiento */ }
  mostrar(pedida || recordada, false);

  /* La cuenta que va en la pestaña de Documentos es la misma que ya
     calcula el checklist. En vez de calcularla otra vez aquí —y arriesgar
     que las dos digan cosas distintas— se copia de donde ya está. */
  var avance = document.getElementById("avance");
  var enPestana = document.getElementById("pestana-conteo");
  if (avance && enPestana) {
    var copiar = function () { enPestana.textContent = avance.textContent; };
    copiar();
    new MutationObserver(copiar).observe(avance, {
      childList: true, characterData: true, subtree: true
    });
  }

  cargar();
})();
