/**
 * Divide un texto en un arreglo de líneas si supera un ancho máximo.
 * @param {string} texto - El texto original de la categoría.
 * @param {number} maxCaracteresPorLinea - Cantidad de caracteres aprox por línea (ej: 15-20).
 * @returns {string|string[]} - Cadena simple o Arreglo de cadenas si superó el límite.
 */
function formatearEtiquetaApex(texto, maxCaracteresPorLinea = 18) {
  if (!texto || texto.length <= maxCaracteresPorLinea) {
    return texto;
  }

  const palabras = texto.split(' ');
  const lineas = [];
  let lineaActual = '';

  for (const palabra of palabras) {
    // Si agregar la palabra supera el límite y ya tenemos contenido en la línea actual
    if ((lineaActual + ' ' + palabra).trim().length > maxCaracteresPorLinea) {
      lineas.push(lineaActual);
      lineaActual = palabra;
    } else {
      lineaActual = lineaActual ? `${lineaActual} ${palabra}` : palabra;
    }
  }

  if (lineaActual) {
    lineas.push(lineaActual);
  }

  return lineas;
}