import { describe, expect, it } from "vitest";

import { elMasSeguido } from "./ejercicios";

const serie = (exercise: string, cargas: (number | null)[]) => ({
  exercise,
  points: cargas.map((load_kg, i) => ({ week: i + 1, load_kg })),
});

describe("qué ejercicio se abre primero", () => {
  it("el que tiene más semanas con carga registrada", () => {
    // Son 59 ejercicios en el catálogo. Abrir en el primero alfabético cae casi
    // siempre en un accesorio que nadie está siguiendo.
    const series = [
      serie("ACCESORIO", [20, null, null]),
      serie("SENTADILLA", [100, 105, 110]),
      serie("OTRO", [null, null, null]),
    ];
    expect(elMasSeguido(series)).toBe("SENTADILLA");
  });

  it("las semanas sin registrar no cuentan para elegirlo", () => {
    // El control: contando puntos en vez de puntos con carga, el ejercicio con
    // más huecos ganaría justamente por estar más vacío.
    const series = [serie("VACIO", [null, null, null, null]), serie("LLENO", [50, 55])];
    expect(elMasSeguido(series)).toBe("LLENO");
  });

  it("sin series no elige nada, en vez de romper", () => {
    expect(elMasSeguido([])).toBeUndefined();
  });
});
