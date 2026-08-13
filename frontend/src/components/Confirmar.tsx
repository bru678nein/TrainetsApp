import { useEffect, useRef, type ReactNode } from "react";

/**
 * «¿Estás seguro?», sobre un `<dialog>` nativo.
 *
 * Nativo por lo mismo que el desplegable de días: el navegador ya resuelve
 * atrapar el foco adentro, cerrar con Escape, dejar el fondo inerte y devolver
 * el foco a donde estaba al cerrar. Un `<div>` con posición fija se ve igual en
 * la captura y no hace nada de eso — y en un diálogo que confirma algo
 * irreversible, «el foco se escapó al fondo» significa que alguien puede
 * apretar Enter sobre un botón que no está mirando.
 *
 * `showModal()` y no el atributo `open`: sólo el primero da el fondo inerte y el
 * cierre con Escape. Es la diferencia entre un diálogo y una caja que flota.
 *
 * El botón que destruye **no** es el que está enfocado al abrir. Confirmar tiene
 * que costar un movimiento; si el foco arranca ahí, un Enter de más borra un
 * ejercicio.
 */
export function Confirmar({
  abierto,
  titulo,
  children,
  confirmar = "Borrar",
  onConfirmar,
  onCancelar,
}: {
  abierto: boolean;
  titulo: string;
  children: ReactNode;
  confirmar?: string;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  const dialogo = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogo.current;
    if (!el) return;
    if (abierto && !el.open) el.showModal();
    if (!abierto && el.open) el.close();
  }, [abierto]);

  return (
    <dialog
      ref={dialogo}
      className="confirmar"
      // Escape y el clic afuera cierran el diálogo por su cuenta; sin esto el
      // estado de React se quedaría creyendo que sigue abierto y no volvería a
      // abrirlo la próxima vez.
      onClose={onCancelar}
      onCancel={onCancelar}
    >
      {/* El contenido se monta recién al abrir. El `<dialog>` queda siempre en el
          árbol porque hace falta la referencia para llamar a `showModal`, pero
          `autoFocus` de React enfoca **al montar**: con los botones montados de
          entrada, abrir la pantalla le robaba el foco a lo que la persona
          estuviera haciendo. */}
      {abierto ? (
        <>
          <h3>{titulo}</h3>
          <div className="confirmar__cuerpo">{children}</div>
          <p className="confirmar__aviso">Esto no se puede deshacer.</p>
          <div className="fila confirmar__acciones">
            <button type="button" onClick={onCancelar} autoFocus>
              Cancelar
            </button>
            <button type="button" className="peligro" onClick={onConfirmar}>
              {confirmar}
            </button>
          </div>
        </>
      ) : null}
    </dialog>
  );
}
