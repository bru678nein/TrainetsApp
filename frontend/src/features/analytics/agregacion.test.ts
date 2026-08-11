import { describe, expect, it } from "vitest";

import { TODOS, patronesDe, porSemana } from "./agregacion";

const fila = (week: number, pattern: string, planned: number, done: number) => ({
  week,
  pattern,
  sets_planned: planned,
  sets_done: done,
  tonnage_kg: 0,
});

const FILAS = [
  fila(1, "isquios", 14, 11),
  fila(1, "cuadriceps", 12, 12),
  fila(2, "isquios", 15, 11),
  fila(2, "cuadriceps", 13, 13),
];

describe("el colapso del eje de patrones", () => {
  it("suma las dos series por semana", () => {
    expect(porSemana(FILAS, TODOS)).toEqual([
      { week: 1, prescrito: 26, hecho: 23 },
      { week: 2, prescrito: 28, hecho: 24 },
    ]);
  });

  it("filtrando por patrón deja sólo ese", () => {
    // Es la pregunta que encadena con la adherencia: esa dice cuál patrón falla,
    // ésta dice en qué semanas se despegó.
    expect(porSemana(FILAS, "isquios")).toEqual([
      { week: 1, prescrito: 14, hecho: 11 },
      { week: 2, prescrito: 15, hecho: 11 },
    ]);
  });

  it("las semanas salen ordenadas aunque lleguen al revés", () => {
    // Recharts dibuja en el orden del array: desordenado, la progresión se lee
    // hacia atrás y el gráfico miente sin errores.
    const alReves = [fila(3, "p", 1, 1), fila(1, "p", 2, 2), fila(2, "p", 3, 3)];
    expect(porSemana(alReves, TODOS).map((p) => p.week)).toEqual([1, 2, 3]);
  });

  it("un patrón inexistente da una serie vacía, no una excepción", () => {
    expect(porSemana(FILAS, "no-existe")).toEqual([]);
  });

  it("los patrones del selector no se repiten y vienen ordenados", () => {
    expect(patronesDe(FILAS)).toEqual(["cuadriceps", "isquios"]);
  });
});
