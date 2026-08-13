import { useId } from "react";

/**
 * Elegir un número de una lista corta: apretás y se abre del 1 al 7.
 *
 * Es un `<select>` nativo y no un menú propio, y eso es la decisión entera. En
 * el celular abre la rueda del sistema —el gesto que la persona ya conoce de
 * todas las demás aplicaciones—, en la computadora abre el desplegable del
 * navegador, y el teclado funciona sin que nadie escriba nada: flechas para
 * moverse, letras para saltar, Enter para elegir.
 *
 * Un menú hecho a mano se ve igual en la captura y cuesta el resto: foco
 * atrapado, cerrar con Escape, no salirse de la pantalla, anunciar el estado a
 * un lector. Todo eso ya está resuelto acá y gratis.
 *
 * Reemplazó primero a un campo numérico con flechas —apuntar a doce píxeles y
 * contar clics— y después a un rango, que para elegir "día 3" obliga a apuntar
 * una posición en vez de tocar el número que se quiere.
 */
export function Selector({
  etiqueta,
  valor,
  onCambio,
  min = 1,
  max,
  sufijo,
}: {
  etiqueta: string;
  valor: number;
  onCambio: (valor: number) => void;
  min?: number;
  max: number;
  sufijo?: string;
}) {
  const id = useId();
  const opciones = Array.from({ length: max - min + 1 }, (_, i) => min + i);

  // Con una sola opción el control no decide nada: un mesociclo de una semana no
  // tiene "qué semana". Se muestra el dato, porque un desplegable de un elemento
  // pide que lo abran para no ofrecer nada.
  if (opciones.length <= 1) {
    return (
      <p className="selector selector--fijo">
        <span className="selector__etiqueta">{etiqueta}</span>
        <strong className="selector__valor">{min}</strong>
        {sufijo ? <small>{sufijo}</small> : null}
      </p>
    );
  }

  return (
    <span className="selector">
      <label className="selector__etiqueta" htmlFor={id}>
        {etiqueta}
      </label>
      <select id={id} value={valor} onChange={(e) => onCambio(Number(e.target.value))}>
        {opciones.map((n) => (
          <option key={n} value={n}>
            {n}
            {sufijo ? ` ${sufijo}` : ""}
          </option>
        ))}
      </select>
    </span>
  );
}
