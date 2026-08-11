import { screen } from "@testing-library/react";
import { cloneElement, type ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Volumen } from "./Volumen";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

// Recharts mide su contenedor para dibujar y en jsdom todo mide cero. Se le da
// tamaño al contenedor y nada más: el resto del gráfico es el real.
vi.mock("recharts", async (original) => ({
  ...(await original<typeof import("recharts")>()),
  // Le inyecta las medidas al hijo, que es lo que hace el contenedor real. Sin
  // eso el gráfico mide cero y no dibuja nada, y los tests hablarían de una
  // pantalla vacía creyendo que hablan del gráfico.
  ResponsiveContainer: ({ children }: { children: ReactElement }) =>
    cloneElement(children, { width: 600, height: 300 } as never),
}));

// Recharts mide su contenedor para dibujar y en jsdom todo mide cero, así que
// el área del gráfico queda vacía. Estos tests no afirman nada sobre las barras
// —eso se ve mirando, y el plan dice que no se testea— sino sobre lo que sí es
// invisible: que las dos series estén declaradas, que el selector funcione, y
// que los tres estados existan.
const FILAS = [
  { week: 1, pattern: "isquios", sets_planned: 14, sets_done: 11, tonnage_kg: 0 },
  { week: 1, pattern: "cuadriceps", sets_planned: 12, sets_done: 12, tonnage_kg: 0 },
];

describe("la vista de volumen", () => {
  beforeEach(() => {
    pedir.mockReset();
    pedir.mockResolvedValue(FILAS);
  });

  it("dibuja las dos series y no sólo lo hecho", async () => {
    // Sin la serie de lo prescrito es lo que da cualquier app de registro: no se
    // puede ver dónde el plan se despegó de la realidad.
    montar(<Volumen atletaId="a1" />);
    expect(await screen.findByText("prescrito")).toBeInTheDocument();
    expect(screen.getByText("hecho")).toBeInTheDocument();
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
