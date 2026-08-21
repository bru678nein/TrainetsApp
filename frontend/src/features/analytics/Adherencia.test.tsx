import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Adherencia } from "./Adherencia";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

/** Los once patrones, con el nombre que declara la tabla. */
const CATALOGO = [
  { code: "pliometria", label_es: "PLIOMETRIA" },
  { code: "bisagra_de_cadera_isquios", label_es: "Bisagra de cadera / isquios" },
  { code: "rodilla_dominante", label_es: "Rodilla dominante" },
];

/** El API contesta según qué se le pida, como el backend. */
function segunLaRuta(datos = REALES) {
  return (ruta: string) =>
    Promise.resolve(ruta.includes("movement-patterns") ? CATALOGO : datos);
}

/** Los números reales de la planilla, en el orden en que los manda el API. */
const REALES = [
  { pattern: "pliometria", sets_planned: 15, sets_done: 0, completion_rate: 0, in_range_rate: 0, avg_rir_deviation: null },
  { pattern: "bisagra_de_cadera_isquios", sets_planned: 226, sets_done: 163, completion_rate: 0.7212, in_range_rate: 0.89, avg_rir_deviation: -0.3 },
  { pattern: "rodilla_dominante", sets_planned: 232, sets_done: 229, completion_rate: 0.9871, in_range_rate: 0.97, avg_rir_deviation: -0.1 },
];

describe("la adherencia por patrón", () => {
  beforeEach(() => {
    pedir.mockReset();
    pedir.mockImplementation(segunLaRuta());
  });

  it("respeta el orden que manda el API y no reordena", async () => {
    // El orden es parte de la respuesta: pone arriba lo que se saltea sin que
    // nadie lo busque. Reordenar acá —alfabético, por ejemplo— lo esconde entre
    // los que cumplen, y crea un segundo lugar donde ese criterio puede cambiar.
    montar(<Adherencia atletaId="a1" />);
    // Se espera al catálogo antes de leer el orden. Sin esto la aserción corre
    // en el instante en que las filas existen pero los nombres todavía no
    // llegaron, y compara contra los códigos por una carrera y no por el orden,
    // que es lo que este caso mira.
    await screen.findByText("PLIOMETRIA");
    const filas = screen.getAllByRole("listitem");
    expect(filas.map((f) => f.textContent)).toEqual([
      expect.stringContaining("PLIOMETRIA"),
      expect.stringContaining("Bisagra de cadera / isquios"),
      expect.stringContaining("Rodilla dominante"),
    ]);
  });

  it("cada porcentaje viene con su denominador", async () => {
    // 0 de 15 y 0 de 226 se dibujan igual y significan
    // cosas opuestas: una es una conducta, la otra es un bloque que recién
    // empieza.
    montar(<Adherencia atletaId="a1" />);
    // Se espera al catálogo antes de leer el orden. Sin esto la aserción corre
    // en el instante en que las filas existen pero los nombres todavía no
    // llegaron, y compara contra los códigos por una carrera y no por el orden,
    // que es lo que este caso mira.
    await screen.findByText("PLIOMETRIA");
    // Las dos cifras y no sólo el total: «0 de 15» se lee sin tener que hacer la
    // cuenta al revés desde el porcentaje.
    const filas = screen.getAllByRole("listitem");
    expect(within(filas[0]!).getByText(/\bde 15 series/)).toBeInTheDocument();
    expect(within(filas[1]!).getByText(/\bde 226 series/)).toBeInTheDocument();
  });

  it("redondea el porcentaje sin inventarlo", async () => {
    montar(<Adherencia atletaId="a1" />);
    // Se espera al catálogo antes de leer el orden. Sin esto la aserción corre
    // en el instante en que las filas existen pero los nombres todavía no
    // llegaron, y compara contra los códigos por una carrera y no por el orden,
    // que es lo que este caso mira.
    await screen.findByText("PLIOMETRIA");
    const filas = screen.getAllByRole("listitem");
    expect(within(filas[1]!).getByText("72%")).toBeInTheDocument();
    expect(within(filas[2]!).getByText("99%")).toBeInTheDocument();
  });

  it("el nombre del patrón sale del catálogo, no de arreglar el código", async () => {
    // La versión anterior lo fabricaba reemplazando guiones bajos, y eso es una
    // segunda fuente para un dato que la base declara. Ninguna regla de texto
    // convierte `bisagra_de_cadera_isquios` en "Bisagra de cadera / isquios", ni
    // `pliometria` en "PLIOMETRIA".
    montar(<Adherencia atletaId="a1" />);
    expect(await screen.findByText("Bisagra de cadera / isquios")).toBeInTheDocument();
    expect(screen.getByText("PLIOMETRIA")).toBeInTheDocument();
  });

  it("un patrón que el catálogo no trae se muestra tal cual", async () => {
    // Feo y honesto. Inventarle una versión "linda" es exactamente lo que este
    // cambio vino a sacar, y encima taparía que el catálogo quedó incompleto.
    pedir.mockImplementation(
      segunLaRuta([
        {
          pattern: "patron_nuevo",
          sets_planned: 10,
          sets_done: 5,
          completion_rate: 0.5,
          in_range_rate: 1,
          avg_rir_deviation: null,
        },
      ]),
    );
    montar(<Adherencia atletaId="a1" />);
    expect(await screen.findByText("patron_nuevo")).toBeInTheDocument();
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
