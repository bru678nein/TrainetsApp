import { useId, useRef, useState, type ReactNode } from "react";

/**
 * Pestañas con el teclado que el patrón pide, que es lo que las hace pestañas y
 * no botones que esconden cosas.
 *
 * La diferencia importa: en una lista de botones, Tab pasa por cada uno. En un
 * grupo de pestañas, Tab entra y sale del grupo entero y **las flechas mueven
 * entre ellas**, porque son una sola elección y no cinco controles. Quien navega
 * con teclado espera eso, y una implementación a medias es peor que ninguna: se
 * ve igual y se comporta distinto.
 *
 * `aria-selected` y `aria-controls` no son decoración tampoco: sin ellos, un
 * lector de pantalla anuncia "botón" y no puede decir cuántas hay ni cuál está
 * activa.
 *
 * El estado vive acá y no en la URL. Es una decisión y tiene un costo: recargar
 * vuelve a la primera. Se elige así porque el editor ya tiene la dirección
 * ocupada por el atleta y el programa, y meter la pestaña ahí adentro convierte
 * cada clic en una entrada del historial — el botón de atrás dejaría de volver
 * al panel del atleta para recorrer pestañas.
 */

export type Pestana = { id: string; titulo: string; contenido: ReactNode };

export function Pestanas({ pestanas }: { pestanas: Pestana[] }) {
  const base = useId();
  const [activa, setActiva] = useState(pestanas[0]?.id);
  const botones = useRef<Record<string, HTMLButtonElement | null>>({});

  const mover = (desde: number, paso: number) => {
    const destino = pestanas[(desde + paso + pestanas.length) % pestanas.length];
    if (!destino) return;
    setActiva(destino.id);
    // El foco sigue a la selección: si se queda atrás, las flechas siguientes
    // parten de donde estaba el foco y no de lo que la persona ve elegido.
    botones.current[destino.id]?.focus();
  };

  return (
    <>
      <div className="pestanas" role="tablist">
        {pestanas.map((p, i) => {
          const seleccionada = p.id === activa;
          return (
            <button
              key={p.id}
              ref={(el) => {
                botones.current[p.id] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-${p.id}`}
              aria-selected={seleccionada}
              aria-controls={`${base}-${p.id}-panel`}
              // Un solo punto de entrada con Tab: el resto se alcanza con las
              // flechas, que es lo que distingue un grupo de una lista.
              tabIndex={seleccionada ? 0 : -1}
              className={`pestanas__boton${seleccionada ? " pestanas__boton--activa" : ""}`}
              onClick={() => setActiva(p.id)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight") mover(i, 1);
                else if (e.key === "ArrowLeft") mover(i, -1);
                else if (e.key === "Home") mover(0, 0);
                else if (e.key === "End") mover(pestanas.length - 1, 0);
                else return;
                e.preventDefault();
              }}
            >
              {p.titulo}
            </button>
          );
        })}
      </div>
      {pestanas.map((p) =>
        p.id === activa ? (
          <div
            key={p.id}
            role="tabpanel"
            id={`${base}-${p.id}-panel`}
            aria-labelledby={`${base}-${p.id}`}
            tabIndex={0}
          >
            {p.contenido}
          </div>
        ) : null,
      )}
    </>
  );
}
