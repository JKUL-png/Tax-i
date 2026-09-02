/* ==========================================================
   El selector de renglones

   Antes esto era un <select> del navegador. Con seis renglones
   funcionaba; con los quince que salen de la exógena más los que el
   contador agregue, la lista se sale de la pantalla y en Windows queda
   cortada contra el borde de la ventana.

   Este lo reemplaza:
     - se escribe para buscar
     - la lista tiene alto fijo y su propio scroll
     - flechas para moverse, Enter para elegir, Escape para salir
     - se puede crear un renglón nuevo sin salir de aquí

   JavaScript plano, sin librerías. Se ve igual en Windows y en Mac
   porque el desplegable lo dibuja la página, no el sistema.
   ========================================================== */

(function () {
  "use strict";

  /* Cuántas opciones se ven antes de que empiece a rodar la lista.
     Más de esto y el desplegable tapaba media pantalla. */
  var ALTO_MAXIMO = 260;

  /* Solo puede haber un desplegable abierto a la vez. */
  var abierto = null;

  function sinTildes(texto) {
    return (texto || "").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function cerrarElAbierto() {
    if (abierto) abierto.cerrar();
  }

  document.addEventListener("click", function (evento) {
    if (abierto && !abierto.caja.contains(evento.target)) cerrarElAbierto();
  });

  /* Crea un selector.

     opciones:
       renglones   lista de {id, titulo}
       elegido     el id que viene puesto, o null
       vacio       qué dice cuando no hay nada elegido
       alElegir    función(id) cuando el contador elige
       alCrear     función(titulo) -> promesa con el renglón nuevo.
                   Si no se pasa, no se ofrece crear.
       etiqueta    para los lectores de pantalla
  */
  function crear(opciones) {
    var renglones = opciones.renglones || [];
    var elegido = opciones.elegido || null;
    var textoVacio = opciones.vacio || "— sin asignar —";

    var caja = document.createElement("div");
    caja.className = "selector-buscable";

    var boton = document.createElement("button");
    boton.type = "button";
    boton.className = "selector-boton";
    boton.setAttribute("aria-haspopup", "listbox");
    boton.setAttribute("aria-expanded", "false");
    if (opciones.etiqueta) boton.setAttribute("aria-label", opciones.etiqueta);

    var desplegable = document.createElement("div");
    desplegable.className = "selector-desplegable";
    desplegable.hidden = true;

    var buscador = document.createElement("input");
    buscador.type = "text";
    buscador.className = "selector-buscador";
    buscador.placeholder = "Escriba para buscar…";
    buscador.setAttribute("aria-label", "Buscar un renglón");

    var lista = document.createElement("div");
    lista.className = "selector-lista";
    lista.setAttribute("role", "listbox");
    lista.style.maxHeight = ALTO_MAXIMO + "px";

    desplegable.appendChild(buscador);
    desplegable.appendChild(lista);
    caja.appendChild(boton);
    caja.appendChild(desplegable);

    var resaltado = -1;
    var visibles = [];

    function tituloDe(id) {
      for (var i = 0; i < renglones.length; i++) {
        if (String(renglones[i].id) === String(id)) return renglones[i].titulo;
      }
      return null;
    }

    function pintarBoton() {
      var titulo = elegido ? tituloDe(elegido) : null;
      boton.textContent = titulo || textoVacio;
      boton.classList.toggle("selector-vacio", !titulo);
      boton.title = titulo || textoVacio;
    }

    function pintarLista() {
      var busca = sinTildes(buscador.value.trim());
      lista.innerHTML = "";
      visibles = [];

      /* La opción de dejarlo sin asignar va siempre de primera: quitar
         una asignación equivocada tiene que ser tan fácil como ponerla. */
      if (!busca) visibles.push({ id: null, titulo: textoVacio, suelta: true });

      renglones.forEach(function (renglon) {
        if (!busca || sinTildes(renglon.titulo).indexOf(busca) !== -1) {
          visibles.push(renglon);
        }
      });

      /* Crear uno nuevo con lo que se escribió, si no existe ya. */
      var escrito = buscador.value.trim();
      if (opciones.alCrear && escrito) {
        var yaEsta = renglones.some(function (r) {
          return sinTildes(r.titulo) === sinTildes(escrito);
        });
        if (!yaEsta) {
          visibles.push({ nuevo: true, titulo: escrito });
        }
      }

      if (visibles.length === 0) {
        var nada = document.createElement("p");
        nada.className = "selector-nada";
        nada.textContent = "Ningún renglón dice eso.";
        lista.appendChild(nada);
        resaltado = -1;
        return;
      }

      visibles.forEach(function (opcion, indice) {
        var fila = document.createElement("button");
        fila.type = "button";
        fila.className = "selector-opcion";
        fila.setAttribute("role", "option");
        if (opcion.nuevo) {
          fila.classList.add("selector-crear");
          fila.textContent = "Crear el renglón «" + opcion.titulo + "»";
        } else {
          fila.textContent = opcion.titulo;
          if (opcion.suelta) fila.classList.add("selector-vacio");
          if (elegido && String(opcion.id) === String(elegido)) {
            fila.classList.add("selector-elegida");
            fila.setAttribute("aria-selected", "true");
          }
        }
        fila.addEventListener("click", function (evento) {
          evento.stopPropagation();
          escoger(indice);
        });
        fila.addEventListener("mousemove", function () {
          resaltar(indice);
        });
        lista.appendChild(fila);
      });

      resaltar(busca ? 0 : -1);
    }

    function resaltar(indice) {
      resaltado = indice;
      var filas = lista.querySelectorAll(".selector-opcion");
      for (var i = 0; i < filas.length; i++) {
        filas[i].classList.toggle("selector-resaltada", i === indice);
      }
      if (indice >= 0 && filas[indice]) {
        var fila = filas[indice];
        if (fila.offsetTop < lista.scrollTop) {
          lista.scrollTop = fila.offsetTop;
        } else if (fila.offsetTop + fila.offsetHeight >
                   lista.scrollTop + lista.clientHeight) {
          lista.scrollTop = fila.offsetTop + fila.offsetHeight
                            - lista.clientHeight;
        }
      }
    }

    function escoger(indice) {
      var opcion = visibles[indice];
      if (!opcion) return;

      if (opcion.nuevo) {
        boton.disabled = true;
        Promise.resolve(opciones.alCrear(opcion.titulo)).then(function (creado) {
          boton.disabled = false;
          if (!creado) return;
          renglones.push(creado);
          elegido = creado.id;
          pintarBoton();
          cerrar();
          if (opciones.alElegir) opciones.alElegir(creado.id);
        }, function () {
          boton.disabled = false;
        });
        return;
      }

      elegido = opcion.id;
      pintarBoton();
      cerrar();
      if (opciones.alElegir) opciones.alElegir(opcion.id);
    }

    function abrir() {
      cerrarElAbierto();
      desplegable.hidden = false;
      boton.setAttribute("aria-expanded", "true");
      buscador.value = "";
      pintarLista();
      buscador.focus();
      abierto = { caja: caja, cerrar: cerrar };
      acomodar();
    }

    function acomodar() {
      /* Si abriendo hacia abajo no cabe, se abre hacia arriba. Pasa en
         las últimas filas de una tabla larga. */
      desplegable.classList.remove("selector-hacia-arriba");
      var sitio = caja.getBoundingClientRect();
      var falta = sitio.bottom + desplegable.offsetHeight + 12
                  > window.innerHeight;
      if (falta && sitio.top > desplegable.offsetHeight) {
        desplegable.classList.add("selector-hacia-arriba");
      }
    }

    function cerrar() {
      desplegable.hidden = true;
      boton.setAttribute("aria-expanded", "false");
      if (abierto && abierto.caja === caja) abierto = null;
    }

    boton.addEventListener("click", function (evento) {
      evento.stopPropagation();
      if (desplegable.hidden) abrir(); else cerrar();
    });

    boton.addEventListener("keydown", function (evento) {
      if (evento.key === "ArrowDown" || evento.key === "Enter") {
        evento.preventDefault();
        abrir();
      }
    });

    buscador.addEventListener("input", pintarLista);

    buscador.addEventListener("keydown", function (evento) {
      if (evento.key === "ArrowDown") {
        evento.preventDefault();
        resaltar(Math.min(resaltado + 1, visibles.length - 1));
      } else if (evento.key === "ArrowUp") {
        evento.preventDefault();
        resaltar(Math.max(resaltado - 1, 0));
      } else if (evento.key === "Enter") {
        evento.preventDefault();
        if (resaltado >= 0) escoger(resaltado);
      } else if (evento.key === "Escape") {
        evento.preventDefault();
        cerrar();
        boton.focus();
      } else if (evento.key === "Tab") {
        cerrar();
      }
    });

    pintarBoton();

    return {
      elemento: caja,
      /* Para volver a pintarlo cuando cambian los renglones sin que
         haya que rehacer toda la fila. */
      actualizar: function (nuevos, nuevoElegido) {
        if (nuevos) renglones = nuevos;
        if (nuevoElegido !== undefined) elegido = nuevoElegido;
        pintarBoton();
      },
      elegido: function () { return elegido; }
    };
  }

  window.SelectorRenglon = { crear: crear };
})();
