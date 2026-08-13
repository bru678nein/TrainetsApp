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
