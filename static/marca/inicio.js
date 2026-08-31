/* ==========================================================
   La portada de inicio

   Escribe "Tax-i" letra por letra, dibuja el logo y lo deja hacer su
   gesto. Dura 2,8 segundos como máximo y sale una sola vez por sesión.

   Por qué tan corta y tan fácil de saltar
   ---------------------------------------
   El contador abre esto veinte veces al día en temporada. Una portada
   que no se puede saltar es de las cosas que más estorban en una
   herramienta de trabajo: la primera vez es bonita y la número quince es
   una piedra en el camino. Por eso:

     - 2.800 ms de tope, contados abajo en la línea de tiempo. El
       segundo y medio de más no es espera: es el logo haciendo su
       gesto —abre los ojos, los entrecierra, guiña—, que es lo que hay
       que ver una vez para entender de qué va la marca.
     - Se corta con un clic o con cualquier tecla.
     - Se guarda en sessionStorage, así que aparece al abrir el programa
       y no vuelve a salir al moverse entre pantallas.
     - Si el sistema pide menos movimiento (prefers-reduced-motion), se
       muestra quieta medio segundo y se va.

   Este archivo se carga en el <head> SIN defer, a propósito: tiene que
   marcar el <html> antes del primer pintado, o se alcanza a ver la
   pantalla de la aplicación un instante antes de que aparezca la
   portada.
   ========================================================== */

(function () {
  "use strict";

  var LLAVE = "taxi-portada-vista";
  var PALABRA = "Tax-i";

  /* --- Los tiempos, en milisegundos desde que arranca --- */
  var POR_LETRA = 130;      // 5 letras = 650 ms escribiendo
  var EMPIEZA_TEXTO = 150;
  var ENTRA_LOGO = 850;     // entra con los dos ojos abiertos
  var ENTRA_SUB = 1150;
  var GESTO_LEYENDO = 1550; // entrecierra
  var GESTO_LISTO = 1950;   // y guiña: el visto, revisado
  var EMPIEZA_SALIDA = 2600;
  var DURA_SALIDA = 200;    // total: 2.800 ms

  var raiz = document.documentElement;

  /* Solo en la lista de clientes, que es por donde se entra al programa.

     Antes salía en las tres páginas y bastaba con que sessionStorage
     estuviera vacío —una pestaña nueva, una ventana privada— para que
     apareciera de golpe en mitad del trabajo, al entrar a un cliente.
     Una portada de arranque tiene que salir al arrancar y en ningún otro
     momento: dentro de un cliente nunca es bienvenida. */
  var camino = location.pathname.replace(/\/+$/, "");
  if (camino !== "" && camino !== "/index.html") return;

  /* ¿Ya se vio en esta sesión? En una ventana privada o con el
     almacenamiento bloqueado, sessionStorage revienta al leerlo: si eso
     pasa se prefiere no mostrar la portada antes que romper la página. */
  var yaVista = true;
  try {
    yaVista = sessionStorage.getItem(LLAVE) === "si";
  } catch (e) {
    yaVista = true;
  }

  if (yaVista) return;

  /* Se marca el <html> ahora mismo, antes de que se pinte nada: es lo
     que hace visible el div de la portada que está en el HTML. */
  raiz.classList.add("portada-corriendo");

  try {
    sessionStorage.setItem(LLAVE, "si");
  } catch (e) {
    /* Sin almacenamiento la portada saldría en cada página. Se prefiere
       eso a que el programa no arranque, y es un caso muy raro. */
  }

  var quietos = window.matchMedia &&
                window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("DOMContentLoaded", function () {
    var portada = document.querySelector(".portada-inicio");
    if (!portada) {
      /* Si por lo que sea no está el div, se quita la marca y la
         aplicación sigue como si nada. */
      raiz.classList.remove("portada-corriendo");
      return;
    }

    var escrito = portada.querySelector(".portada-escrito");
    var relojes = [];
    var terminada = false;

    function despues(ms, hacer) {
      relojes.push(window.setTimeout(hacer, ms));
    }

    /* Quitar la portada. Se puede llamar dos veces sin que pase nada. */
    function cerrar() {
      if (terminada) return;
      terminada = true;

      relojes.forEach(window.clearTimeout);
      document.removeEventListener("keydown", saltar, true);
      document.removeEventListener("pointerdown", saltar, true);

      portada.classList.add("portada-saliendo");
      window.setTimeout(function () {
        raiz.classList.remove("portada-corriendo");
        if (portada.parentNode) portada.parentNode.removeChild(portada);
      }, quietos ? 0 : DURA_SALIDA);
    }

    function saltar() {
      cerrar();
    }

    /* Cualquier tecla y cualquier clic la cortan. En captura, para que
       ningún otro manejador se los coma antes. */
    document.addEventListener("keydown", saltar, true);
    document.addEventListener("pointerdown", saltar, true);

    /* --- Sin movimiento: se muestra el estado final y se va --- */
    if (quietos) {
      if (escrito) escrito.textContent = PALABRA;
      portada.classList.add("portada-quieta");
      despues(500, cerrar);
      return;
    }

    /* --- Con movimiento: la máquina de escribir --- */
    for (var i = 1; i <= PALABRA.length; i++) {
      (function (letras) {
        despues(EMPIEZA_TEXTO + letras * POR_LETRA, function () {
          if (escrito) escrito.textContent = PALABRA.slice(0, letras);
        });
      })(i);
    }

    var logo = portada.querySelector(".portada-logo");
    var marca = window.MarcaTaxi;

    /* El logo entra con los dos ojos abiertos y termina guiñando. Ese
       recorrido es el que explica la marca sin una sola palabra. */
    if (marca) marca.gesto(logo, "esperando");

    despues(ENTRA_LOGO, function () { portada.classList.add("portada-con-logo"); });
    despues(ENTRA_SUB, function () { portada.classList.add("portada-con-sub"); });
    if (marca) {
      despues(GESTO_LEYENDO, function () { marca.gesto(logo, "leyendo"); });
      despues(GESTO_LISTO, function () { marca.gesto(logo, "listo"); });
    }
    despues(EMPIEZA_SALIDA, cerrar);
  });
})();
