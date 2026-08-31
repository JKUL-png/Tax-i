/* ==========================================================
   El arranque de la pantalla del cliente.

   Va de último a propósito: todos los demás archivos ya definieron sus
   funciones, así que aquí solo queda decir en qué orden se piden las
   cosas. Antes esto estaba repartido en cuatro sitios del archivo
   grande y era imposible saber qué corría primero.
   ========================================================== */

if (!idCliente) {
  tituloNombre.textContent = "Falta el cliente";
  lineaDatos.textContent = "Vuelva a la lista y entre a un cliente.";
} else {
  cargarCliente();
  cargarVecinos();
  cargarConfiguracion();
  cargarHistorial();

  // Primero el checklist y DESPUÉS los documentos: el selector de cada
  // documento se arma con los renglones, así que tienen que existir ya.
  cargarChecklist().then(cargarDocumentos);
}

recordarPlegables();
