/* ==========================================================
   La portada de la pantalla de inicio

   Escribe "Tax-i" letra por letra, deja caer el logo, abre la frase que
   define el programa y termina con el guiño del logo. Dura 2,1 segundos
   y no tapa nada: es la pantalla de inicio, no un telón encima de ella.

   Qué era antes y por qué cambió
   ------------------------------
   Esto era una portada a pantalla completa que salía una vez por sesión
   y había que saltarse con un clic. Se quitó cuando la misma animación
   pasó a vivir fija en la pantalla de inicio: con las dos puestas se veía
   dos veces seguidas —el telón encima y, al quitarse, otra vez debajo—.
   La pantalla de inicio es la entrada del programa; no necesita un telón
   delante. Ya no hay nada que saltar, nada que recordar en sessionStorage
   y nada que tape la aplicación.

   Este archivo se carga en el <head> SIN defer, a propósito: tiene que
   marcar el <html> antes del primer pintado. Esa marca es la que esconde
   las letras; sin ella se alcanza a ver "Tax-i" completo un instante
   antes de que empiece a escribirse.

   Si el JavaScript no corre, la marca nunca se pone: la portada se ve
   quieta y completa. Es la falla correcta para una animación.
   ========================================================== */

(function () {
  "use strict";

  /* La palabra, partida donde cambia de color: "Tax" en tinta y "-i" en
     verde. Se escribe de corrido, pero son dos trozos porque el verde de
     la "-i" es parte de la marca y se perdería si esto fuera un solo
     texto plano. */
  var PARTE_UNO = "Tax";
  var PARTE_DOS = "-i";
  var LETRAS = PARTE_UNO.length + PARTE_DOS.length;

  /* --- Los tiempos, en milisegundos desde que arranca --- */
  var EMPIEZA_TEXTO = 180;
  var POR_LETRA = 130;      // 5 letras = 650 ms escribiendo
  var ENTRA_LOGO = 900;     // el logo cae cuando el nombre ya está escrito
  var ENTRA_FRASE = 1200;   // la definición y la doble raya
  var ENTRA_RESTO = 1500;   // la cuenta de clientes y el indicio de abajo
  var GESTO_LEYENDO = 1750; // entrecierra los ojos
  var GESTO_LISTO = 2100;   // y guiña: el visto, revisado

  var raiz = document.documentElement;

  /* Solo en la pantalla de inicio. El <script> ya no está en las demás
     páginas, pero la comprobación se queda: si alguien lo vuelve a pegar
     en otra, no pasa nada. */
  var camino = location.pathname.replace(/\/+$/, "");
  if (camino !== "" && camino !== "/index.html") return;

  /* Se marca el <html> ahora mismo, antes de que se pinte nada. */
  raiz.classList.add("inicio-animada");

  var quietos = window.matchMedia &&
                window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.addEventListener("DOMContentLoaded", function () {
    var uno = document.querySelector(".inicio-parte-uno");
    var dos = document.querySelector(".inicio-parte-dos");
    var logo = document.querySelector(".inicio-logo");

    /* Si por lo que sea no están los trozos del nombre, se quita la marca
       y la pantalla queda completa y quieta. Nunca escondida. */
    if (!uno || !dos) {
      raiz.classList.remove("inicio-animada");
      return;
    }

    /* Todo encendido de una vez. Es el estado final de la animación. */
    function mostrarTodo() {
      uno.textContent = PARTE_UNO;
      dos.textContent = PARTE_DOS;
      raiz.classList.add("inicio-escribiendo", "inicio-con-logo",
                         "inicio-con-frase", "inicio-lista");
    }

    /* --- Sin movimiento: el estado final y ya --- */
    if (quietos) {
      mostrarTodo();
      return;
    }

    /* --- Con movimiento: la máquina de escribir --- */

    /* Las letras arrancan vacías y la caja se hace visible: hasta aquí
       estaban escondidas por CSS, no borradas, para que sin JavaScript se
       leyeran completas. */
    uno.textContent = "";
    dos.textContent = "";
    raiz.classList.add("inicio-escribiendo");

    function escribir(cuantas) {
      uno.textContent = PARTE_UNO.slice(0, cuantas);
      dos.textContent = cuantas > PARTE_UNO.length
        ? PARTE_DOS.slice(0, cuantas - PARTE_UNO.length)
        : "";
    }

    function despues(ms, hacer) {
      window.setTimeout(hacer, ms);
    }

    for (var i = 1; i <= LETRAS; i++) {
      (function (cuantas) {
        despues(EMPIEZA_TEXTO + cuantas * POR_LETRA, function () {
          escribir(cuantas);
        });
      })(i);
    }

    despues(ENTRA_LOGO,  function () { raiz.classList.add("inicio-con-logo"); });
    despues(ENTRA_FRASE, function () { raiz.classList.add("inicio-con-frase"); });
    despues(ENTRA_RESTO, function () { raiz.classList.add("inicio-lista"); });

    /* El logo entra con los dos ojos abiertos y termina guiñando. Ese
       recorrido es el que explica la marca sin una sola palabra. De aquí
       en adelante lo sigue haciendo parpadear marca.js. */
    var marca = window.MarcaTaxi;
    if (marca) {
      marca.gesto(logo, "esperando");
      despues(GESTO_LEYENDO, function () { marca.gesto(logo, "leyendo"); });
      despues(GESTO_LISTO,   function () { marca.gesto(logo, "listo"); });
    }
  });
})();
