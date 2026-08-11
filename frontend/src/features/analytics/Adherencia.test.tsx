import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Adherencia } from "./Adherencia";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

/** Los números reales de la planilla, en el orden en que los manda el API. */
const REALES = [
  { pattern: "pliometria", sets_planned: 15, sets_done: 0, completion_rate: 0, in_range_rate: 0, avg_rir_deviation: null },
  { pattern: "bisagra_de_cadera_isquios", sets_planned: 226, sets_done: 163, completion_rate: 0.7212, in_range_rate: 0.89, avg_rir_deviation: -0.3 },
  { pattern: "rodilla_dominante", sets_planned: 232, sets_done: 229, completion_rate: 0.9871, in_range_rate: 0.97, avg_rir_deviation: -0.1 },
];

describe("la adherencia por patrón", () => {
  beforeEach(() => {
    pedir.mockReset();
    pedir.mockResolvedValue(REALES);
  });

  it("respeta el orden que manda el API y no reordena", async () => {
    // El orden es parte de la respuesta: pone arriba lo que se saltea sin que
    // nadie lo busque. Reordenar acá —alfabético, por ejemplo— lo esconde entre
    // los que cumplen, y crea un segundo lugar donde ese criterio puede cambiar.
    montar(<Adherencia atletaId="a1" />);
    const filas = await screen.findAllByRole("listitem");
    expect(filas.map((f) => f.textContent)).toEqual([
      expect.stringContaining("pliometria"),
      expect.stringContaining("bisagra de cadera isquios"),
      expect.stringContaining("rodilla dominante"),
    ]);
  });

  it("cada porcentaje viene con su denominador", async () => {
    // Criterio 3 de la spec. 0 de 15 y 0 de 226 se dibujan igual y significan
    // cosas opuestas: una es una conducta, la otra es un bloque que recién
    // empieza.
    montar(<Adherencia atletaId="a1" />);
    const filas = await screen.findAllByRole("listitem");
    expect(within(filas[0]!).getByText("de 15")).toBeInTheDocument();
    expect(within(filas[1]!).getByText("de 226")).toBeInTheDocument();
  });

  it("redondea el porcentaje sin inventarlo", async () => {
    montar(<Adherencia atletaId="a1" />);
    const filas = await screen.findAllByRole("listitem");
    expect(within(filas[1]!).getByText("72%")).toBeInTheDocument();
    expect(within(filas[2]!).getByText("99%")).toBeInTheDocument();
  });

  it("el patrón se lee, no viene con guiones bajos", async () => {
    montar(<Adherencia atletaId="a1" />);
    expect(await screen.findByText("bisagra de cadera isquios")).toBeInTheDocument();
  });

  it("mientras carga lo dice", () => {
    pedir.mockReturnValue(new Promise(() => {}));
    montar(<Adherencia atletaId="a1" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("si falla lo dice", async () => {
    pedir.mockRejectedValue(new Error("403"));
    montar(<Adherencia atletaId="a1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("sin series prescritas explica por qué está vacío", async () => {
    pedir.mockResolvedValue([]);
    montar(<Adherencia atletaId="a1" />);
    expect(
      await screen.findByText("Este atleta todavía no tiene series prescritas."),
    ).toBeInTheDocument();
  });
});
