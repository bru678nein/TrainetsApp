import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { cloneElement, type ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Progresion } from "./Progresion";

const pedir = vi.hoisted(() => vi.fn());
vi.mock("../../api/useApi", () => ({ useApi: () => pedir }));

vi.mock("recharts", async (original) => ({
  ...(await original<typeof import("recharts")>()),
  ResponsiveContainer: ({ children }: { children: ReactElement }) =>
    cloneElement(children, { width: 600, height: 300 } as never),
}));

/** La semana 2 estaba prescrita y no se registró: tiene que quedar como hueco. */
const SERIES = [
  { exercise: "ACCESORIO", points: [{ week: 1, load_kg: 20 }] },
  {
    exercise: "SENTADILLA",
    points: [
      { week: 1, load_kg: 100 },
      { week: 2, load_kg: null },
      { week: 3, load_kg: 105 },
    ],
  },
];

describe("la progresión de carga", () => {
  beforeEach(() => {
    pedir.mockReset();
    pedir.mockResolvedValue(SERIES);
  });

  it("abre en el ejercicio con más semanas registradas", async () => {
    montar(<Progresion atletaId="a1" />);
    expect(await screen.findByRole("combobox")).toHaveValue("SENTADILLA");
  });

  it("la semana sin registrar no se dibuja como un punto", async () => {
    // Lo que separa "no hay dato" de "levantó cero". Un cero afirma algo sobre
    // el peso; el hueco afirma que no hay nada que afirmar.
    const { container } = montar(<Progresion atletaId="a1" />);
    await screen.findByRole("combobox");
    expect(container.querySelectorAll(".recharts-line-dot")).toHaveLength(2);
  });

  it("la línea se corta en el hueco en vez de saltarlo", async () => {
    // Ésta es la afirmación que sostiene la vista entera, y contar puntos no la
    // hace: con la línea conectada los puntos siguen siendo dos y el gráfico se
    // lee como una progresión continua que nunca ocurrió.
    //
    // Un trazado con hueco arranca dos veces —dos comandos `M`—; uno continuo,
    // una sola.
    const { container } = montar(<Progresion atletaId="a1" />);
    await screen.findByRole("combobox");
    const trazado = container.querySelector(".recharts-line-curve")?.getAttribute("d") ?? "";
    expect(trazado.match(/M/g) ?? []).toHaveLength(2);
  });

  it("se puede cambiar de ejercicio", async () => {
    montar(<Progresion atletaId="a1" />);
    const selector = await screen.findByRole("combobox");
    await userEvent.selectOptions(selector, "ACCESORIO");
    expect(selector).toHaveValue("ACCESORIO");
  });

  it("sin cargas registradas explica por qué", async () => {
    pedir.mockResolvedValue([]);
    montar(<Progresion atletaId="a1" />);
    expect(
      await screen.findByText("Todavía no hay cargas registradas para este atleta."),
    ).toBeInTheDocument();
  });

  it("si falla lo dice", async () => {
    pedir.mockRejectedValue(new Error("403"));
    montar(<Progresion atletaId="a1" />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
