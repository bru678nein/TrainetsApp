import { useState, type ReactNode } from "react";

/**
 * Una lista que se reordena arrastrando, y también sin arrastrar.
 *
 * Los botones no son un adorno de accesibilidad: **arrastrar es un gesto que
 * mucha gente no puede hacer**, y no sólo quien usa teclado o lector de
 * pantalla. Un trackpad con el dedo tembloroso, una pantalla táctil que no
 * dispara los eventos de arrastre del navegador, o un ejercicio a doce filas de
 * distancia — todos terminan en el mismo lugar. Si el orden sólo se puede
 * cambiar arrastrando, para esas personas el orden no se puede cambiar.
 *
 * Usa arrastre nativo del navegador y no una librería. Para una lista corta
 * dentro de una sesión —tres a seis ejercicios— alcanza y sobra, y una
 * dependencia de reordenado trae su propio modelo de sensores, colisiones y
 * accesibilidad que hay que aprender para usar el 5%.
 *
 * El orden se guarda **completo y no como un movimiento**: el endpoint recibe la
 * lista entera. Eso hace la operación idempotente y deja que el servidor
 * verifique que están todos; un "movete a la posición 3" obliga a saber qué
 * había en 3, y dos pestañas abiertas lo saben distinto.
 */

export type Ordenable = { id: string };

export function ListaOrdenable<T extends Ordenable>({
  elementos,
  onOrdenar,
  deshabilitado = false,
  children,
}: {
  elementos: T[];
  onOrdenar: (ids: string[]) => void;
  deshabilitado?: boolean;
  children: (elemento: T, indice: number) => ReactNode;
}) {
  const [agarrado, setAgarrado] = useState<string | null>(null);
  const [encima, setEncima] = useState<string | null>(null);

  const mover = (desde: number, hasta: number) => {
    if (hasta < 0 || hasta >= elementos.length || desde === hasta) return;
    const ids = elementos.map((e) => e.id);
    const [sacado] = ids.splice(desde, 1);
    if (sacado === undefined) return;
    ids.splice(hasta, 0, sacado);
    onOrdenar(ids);
  };

  const soltarSobre = (destino: string) => {
    const desde = elementos.findIndex((e) => e.id === agarrado);
    const hasta = elementos.findIndex((e) => e.id === destino);
    setAgarrado(null);
    setEncima(null);
    if (desde >= 0 && hasta >= 0) mover(desde, hasta);
  };

  return (
    <ol className="ordenable">
      {elementos.map((elemento, indice) => (
        <li
          key={elemento.id}
          draggable={!deshabilitado}
          onDragStart={() => setAgarrado(elemento.id)}
          onDragEnd={() => {
            setAgarrado(null);
            setEncima(null);
          }}
          // `preventDefault` acá no es ritual: sin él el navegador rechaza el
          // soltar y el evento `drop` no llega nunca.
          onDragOver={(e) => {
            e.preventDefault();
            if (encima !== elemento.id) setEncima(elemento.id);
          }}
          onDrop={(e) => {
            e.preventDefault();
            soltarSobre(elemento.id);
          }}
          className={
            [agarrado === elemento.id ? "agarrado" : "", encima === elemento.id ? "encima" : ""]
              .filter(Boolean)
              .join(" ") || undefined
          }
        >
          <span className="asa" aria-hidden="true" title="Arrastrá para reordenar">
            ⠿
          </span>{" "}
          <button
            type="button"
            onClick={() => mover(indice, indice - 1)}
            disabled={deshabilitado || indice === 0}
            aria-label={`Subir al lugar ${indice}`}
          >
            ↑
          </button>{" "}
          <button
            type="button"
            onClick={() => mover(indice, indice + 1)}
            disabled={deshabilitado || indice === elementos.length - 1}
            aria-label={`Bajar al lugar ${indice + 2}`}
          >
            ↓
          </button>{" "}
          {/* El contenido va envuelto para que el asa y las flechas queden a su
              izquierda en la misma fila. Suelto, cada elemento que devuelva
              `children` sería un hijo más del renglón y lo que venga después del
              primero se va abajo. */}
          <div className="ordenable__contenido">{children(elemento, indice)}</div>
        </li>
      ))}
    </ol>
  );
}
