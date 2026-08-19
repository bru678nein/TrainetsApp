/**
 * Íconos como SVG en línea, no como emoji ni como fuente de íconos.
 *
 * El emoji parecía gratis y no lo es: cada sistema lo dibuja distinto —en unos
 * es un tacho gris, en otros uno azul con tapa— así que el mismo botón no se ve
 * igual en dos máquinas, no toma el color del texto que lo rodea, y su tamaño
 * depende de la fuente que resolvió el sistema.
 *
 * En línea y no una librería: son dos trazos. Una dependencia de íconos trae
 * cientos que no se usan y un `<use>` con sprite agrega un pedido de red para
 * ahorrar cien bytes.
 *
 * `currentColor` y `1em` hacen que hereden color y tamaño de donde estén, así el
 * botón de borrar se pone del color de alerta al pasar el mouse sin que el ícono
 * tenga que enterarse.
 */

type Props = { className?: string };

const base = {
  width: "1em",
  height: "1em",
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  // Decorativo: lo que el botón significa lo dice su `aria-label`, y anunciar
  // "imagen" antes del nombre sólo agrega ruido.
  "aria-hidden": true,
  focusable: false,
};

export function Tacho({ className }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M2.5 4h11" />
      <path d="M6.5 4V2.5h3V4" />
      <path d="M4 4l.6 8.4a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9L12 4" />
      <path d="M6.7 6.8v4M9.3 6.8v4" />
    </svg>
  );
}

export function Mas({ className }: Props) {
  return (
    <svg {...base} className={className}>
      <path d="M8 3.5v9M3.5 8h9" />
    </svg>
  );
}


/**
 * La marca: un bloque macizo al que le falta un pedazo.
 *
 * El bloque es lo que el entrenador planificó; el hueco, lo que no llegó a
 * hacerse. La distancia entre esas dos cosas es de lo que se trata el producto,
 * y acá es literalmente la forma.
 *
 * `currentColor` y no un color propio: en la barra hereda la tinta, y el mismo
 * archivo sirve calado sobre un fondo de color sin una segunda versión. El
 * favicon sí lleva el color literal, porque el navegador lo dibuja fuera de
 * todo documento y ahí `currentColor` no resuelve contra nada.
 */
export function Marca({ tam = 22 }: { tam?: number }) {
  return (
    <svg width={tam} height={tam} viewBox="0 0 32 32" fill="currentColor" aria-hidden="true">
      <path d="M8 3h9v11h11v9a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6V9a6 6 0 0 1 5-6z" />
    </svg>
  );
}
