import type { VolumenSemanal } from "../../api/consultas";

// Este archivo se llamaba `volumen.ts`, al lado de `Volumen.tsx`. En macOS el
// sistema de archivos no distingue mayúsculas, así que `import "./volumen"`
// resolvía al componente: se importaba a sí mismo y todo lo que exportaba
// quedaba indefinido. El error que sale es "Element type is invalid" y apunta a
// React, que no tiene nada que ver.

export type PuntoSemanal = { week: number; prescrito: number; hecho: number };

export const TODOS = "__todos__";

/**
 * Weekly totals, optionally for a single movement pattern.
 *
 * Adding up rows the API already computed is presentation, not analysis — the
 * counting happens in the domain and arrives here decided. What this does is
 * collapse the pattern axis, which is the axis the screen cannot show: eleven
 * stacked colours are unreadable, and picking one pattern answers the question
 * the adherence view raises. That one says which pattern is failing; this one
 * says when it came apart.
 */
export function porSemana(filas: VolumenSemanal[], patron: string): PuntoSemanal[] {
  const acc = new Map<number, PuntoSemanal>();
  for (const fila of filas) {
    if (patron !== TODOS && fila.pattern !== patron) continue;
    const punto = acc.get(fila.week) ?? { week: fila.week, prescrito: 0, hecho: 0 };
    punto.prescrito += fila.sets_planned;
    punto.hecho += fila.sets_done;
    acc.set(fila.week, punto);
  }
  return [...acc.values()].sort((a, b) => a.week - b.week);
}

/** Los patrones presentes, para el selector. Ordenados y sin repetir. */
export function patronesDe(filas: VolumenSemanal[]): string[] {
  return [...new Set(filas.map((f) => f.pattern))].sort();
}
