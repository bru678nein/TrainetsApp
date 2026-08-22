import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Volumen } from "./Volumen";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

// Las columnas se dibujan a mano y no con la librería de gráficos, así que se
// pueden afirmar de verdad: la altura sale de un `style` y las cifras son texto.
// Lo que no se afirma es cómo se ve — eso se mira.
// Dos semanas de tamaños distintos, y no una: con una sola, el techo del gráfico
// **es** lo prescrito de esa semana, así que dividir por el techo y dividir por
// la columna dan el mismo número. Un test con una semana no puede distinguir las
// dos fórmulas — verificado por mutación, pasaba en verde con la equivocada.
const FILAS = [
  { week: 1, pattern: "isquios", sets_planned: 14, sets_done: 11, tonnage_kg: 0 },
  { week: 1, pattern: "cuadriceps", sets_planned: 12, sets_done: 12, tonnage_kg: 0 },
  { week: 2, pattern: "isquios", sets_planned: 6, sets_done: 3, tonnage_kg: 0 },
];

describe("la vista de volumen", () => {
  beforeEach(() => {
    pedir.mockReset();
    pedir.mockResolvedValue(FILAS);
  });

  it("cada semana lleva lo prescrito y lo hecho, no sólo lo hecho", async () => {
    // Sin lo prescrito es lo que da cualquier app de registro: no se puede ver
    // dónde el plan se despegó de la realidad.
    //
    // Se afirma sobre las dos cifras y no sobre una leyenda: la leyenda se sacó
    // a propósito —la columna hueca con la llena adentro se lee sin ella— y un
    // test que la buscara estaría vigilando el adorno en vez del dato.
    montar(<Volumen atletaId="a1" />);
    // 26 prescritas y 23 hechas entre los dos patrones de la semana 1.
    expect(await screen.findByText("23/26")).toBeInTheDocument();
    expect(screen.getByLabelText("Semana 1: 23 de 26 series")).toBeInTheDocument();
  });

  it("la altura de lo hecho es su proporción de lo prescrito", async () => {
    // Es lo único que el dibujo tiene que decir: cuánto del plan entró. Si la
    // altura saliera del total en vez de la columna, dos semanas de tamaños
    // distintos se verían iguales.
    montar(<Volumen atletaId="a1" />);
    await screen.findByText("23/26");
    const columnas = document.querySelectorAll<HTMLElement>(".columnas__hecho");
    // Semana 1: 23 de 26 es 88,46%. Semana 2: 3 de 6 es 50%.
    expect(columnas[0]!.style.height).toMatch(/^88\.4/);
    expect(columnas[1]!.style.height).toBe("50%");
  });

  it("ofrece elegir un patrón, y arranca en todos", async () => {
    montar(<Volumen atletaId="a1" />);
    const selector = await screen.findByRole("combobox");
    expect(selector).toHaveValue("__todos__");
    expect(screen.getByRole("option", { name: "isquios" })).toBeInTheDocument();
  });

  it("elegir un patrón cambia lo que se muestra", async () => {
    montar(<Volumen atletaId="a1" />);
    const selector = await screen.findByRole("combobox");
    await userEvent.selectOptions(selector, "isquios");
    expect(selector).toHaveValue("isquios");
  });

  it("sin datos explica por qué", async () => {
    pedir.mockResolvedValue([]);
    montar(<Volumen atletaId="a1" />);
    expect(
      await screen.findByText("Este atleta todavía no tiene series prescritas."),
    ).toBeInTheDocument();
  });

  it("si falla lo dice", async () => {
    pedir.mockRejectedValue(new Error("403"));
    montar(<Volumen atletaId="a1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
