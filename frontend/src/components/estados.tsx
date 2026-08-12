import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function Cargando({ que }: { que: string }) {
  return (
    <p className="estado" role="status">
      Cargando {que}…
    </p>
  );
}

export function Falla({ que }: { que: string }) {
  return (
    <p className="estado estado--falla" role="alert">
      No se pudo cargar {que}.
    </p>
  );
}

/**
 * The empty state, the most important of the three.
 *
 * It takes a reason and not a title, because "no data" is what every empty
 * screen in every application says and it answers nothing. Here the difference
 * is real and actionable: a panel with no sets logged is waiting for the athlete,
 * while a coach with no athletes is waiting for the coach. Same emptiness, two
 * different next steps.
 */
export function Vacio({ motivo }: { motivo: string }) {
  return <p className="estado">{motivo}</p>;
}

/**
 * The three states in one place, so that no view derives them again.
 *
 * Written by hand per screen, the mistakes repeat: the spinner that never
 * resolves because the error branch was forgotten, the empty list rendered as an
 * empty box, the stale error left on screen after a retry. None of those show up
 * while developing against data that loads instantly.
 */
export function Consulta<T>({
  consulta,
  que,
  vacio,
  children,
}: {
  consulta: UseQueryResult<T>;
  que: string;
  vacio?: { cuando: (datos: T) => boolean; motivo: string };
  children: (datos: T) => ReactNode;
}) {
  if (consulta.isPending) return <Cargando que={que} />;
  if (consulta.isError) return <Falla que={que} />;
  if (vacio?.cuando(consulta.data)) return <Vacio motivo={vacio.motivo} />;
  return <>{children(consulta.data)}</>;
}
