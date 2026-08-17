import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

/**
 * Avisos cortos abajo a la izquierda: «Serie agregada», «Semana duplicada».
 *
 * El editor guarda contra el servidor y vuelve a pedir el árbol entero, así que
 * lo único que confirmaba que algo pasó era ver la lista cambiar. Cuando el
 * cambio queda fuera de la pantalla —duplicar la semana 1 en la 3, borrar una
 * serie de un ejercicio que quedó arriba— no hay ninguna señal, y la duda lleva
 * a apretar de nuevo.
 *
 * Tres decisiones que no son estéticas:
 *
 * - **La región vive siempre en el árbol, aunque esté vacía.** Un lector de
 *   pantalla observa un `aria-live` que ya existe; si el contenedor aparece
 *   junto con el primer mensaje, hay lectores que no anuncian nada porque no
 *   había nada que observar cuando cambió.
 * - **`polite` y no `assertive`.** Confirmar lo que la persona acaba de pedir no
 *   justifica interrumpirle la lectura. `assertive` se reserva para lo que no
 *   puede esperar, y gastarlo acá lo vuelve ruido.
 * - **El texto no se lee solo del `role`.** Cada aviso trae la palabra que dice
 *   si salió bien o mal; el color no viaja al lector, y en una pantalla con luz
 *   de sol tampoco viaja al ojo.
 */

export type TipoDeAviso = "bien" | "mal";

type Aviso = { id: number; texto: string; tipo: TipoDeAviso };

const Contexto = createContext<((texto: string, tipo?: TipoDeAviso) => void) | null>(null);

/** Cuánto queda en pantalla. Lo suficiente para leerlo sin quedarse tapando. */
const DURACION = 4000;

export function ProveedorDeAvisos({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  // Un contador y no la hora: dos avisos en el mismo milisegundo comparten
  // `key`, y React reusa el nodo del primero en vez de agregar el segundo.
  const proximo = useRef(0);
  const relojes = useRef<ReturnType<typeof setTimeout>[]>([]);

  const cerrar = useCallback((id: number) => {
    setAvisos((previos) => previos.filter((a) => a.id !== id));
  }, []);

  const avisar = useCallback(
    (texto: string, tipo: TipoDeAviso = "bien") => {
      const id = proximo.current++;
      setAvisos((previos) => [...previos, { id, texto, tipo }]);
      relojes.current.push(setTimeout(() => cerrar(id), DURACION));
    },
    [cerrar],
  );

  // Los temporizadores pendientes se cancelan al desmontar: si no, disparan
  // sobre un componente que ya no está y React avisa por consola en desarrollo.
  useEffect(() => {
    const pendientes = relojes;
    return () => {
      pendientes.current.forEach(clearTimeout);
      pendientes.current = [];
    };
  }, []);

  return (
    <Contexto.Provider value={avisar}>
      {children}
      {/* `aria-live` sin `role="status"`, y no es un rodeo para evitar un choque
          de selectores. `status` implica `aria-atomic="true"`: cada cambio hace
          releer la región **entera**, así que agregar el segundo aviso vuelve a
          anunciar el primero. Con `aria-atomic` en su valor por defecto se
          anuncia sólo lo que se agregó, que es lo que se quiere en una pila. */}
      <div className="avisos" aria-live="polite" aria-label="Avisos">
        {avisos.map((aviso) => (
          <div key={aviso.id} className={`aviso aviso--${aviso.tipo}`}>
            <span className="aviso__texto">{aviso.texto}</span>
            <button
              type="button"
              className="aviso__cerrar"
              onClick={() => cerrar(aviso.id)}
              aria-label={`Cerrar el aviso «${aviso.texto}»`}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}

/**
 * Devuelve una función sin efecto cuando no hay proveedor.
 *
 * Un `throw` obligaría a envolver cada test que monta un pedazo suelto del
 * editor, y el costo de equivocarse acá es que no se ve un aviso — no que se
 * pierda un dato. Que una prueba de otra cosa reviente por esto sería peor.
 */
export function useAvisar(): (texto: string, tipo?: TipoDeAviso) => void {
  const desdeElContexto = useContext(Contexto);
  const sinProveedor = useCallback(() => {}, []);
  return desdeElContexto ?? sinProveedor;
}
