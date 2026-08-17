import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProveedorDeAvisos, useAvisar } from "./Avisos";

function Boton({ texto, tipo }: { texto: string; tipo?: "bien" | "mal" }) {
  const avisar = useAvisar();
  return (
    <button type="button" onClick={() => avisar(texto, tipo)}>
      disparar {texto}
    </button>
  );
}

const montar = (ui = <Boton texto="Serie agregada" />) =>
  render(<ProveedorDeAvisos>{ui}</ProveedorDeAvisos>);

describe("los avisos", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("la región existe desde el principio, aunque no haya ningún aviso", () => {
    // No es un detalle de implementación. Un lector de pantalla observa un
    // `aria-live` que ya está en el árbol; si el contenedor apareciera junto con
    // el primer mensaje, hay lectores que no anuncian nada. Esto se rompe
    // callado: en pantalla se ve idéntico.
    montar();
    const region = screen.getByLabelText("Avisos");
    // `toBeVisible` y no `toBeInTheDocument`: una región viva marcada `hidden`
    // sigue estando en el árbol y no se anuncia. Estar no alcanza.
    expect(region).toBeVisible();
    expect(region).toHaveAttribute("aria-live", "polite");
    // Sin `aria-atomic`: con la región marcada como atómica, cada aviso nuevo
    // hace releer los que ya estaban.
    expect(region).not.toHaveAttribute("aria-atomic", "true");
    expect(region).toBeEmptyDOMElement();
  });

  it("muestra el texto que se le pide", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    expect(screen.getByText("Serie agregada")).toBeInTheDocument();
  });

  it("se va solo", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    expect(screen.getByText("Serie agregada")).toBeInTheDocument();

    act(() => void vi.advanceTimersByTime(4000));
    expect(screen.queryByText("Serie agregada")).not.toBeInTheDocument();
  });

  it("se puede cerrar antes", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    await userEvent.click(screen.getByRole("button", { name: /Cerrar el aviso/ }));
    expect(screen.queryByText("Serie agregada")).not.toBeInTheDocument();
  });

  it("dos avisos seguidos conviven, y no se pisa uno con otro", async () => {
    // Con la hora como clave, dos avisos del mismo milisegundo comparten `key`
    // y React reusa el nodo del primero: el segundo no aparece nunca.
    montar(
      <>
        <Boton texto="Serie agregada" />
        <Boton texto="Semana duplicada" />
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: /disparar Serie agregada/ }));
    await userEvent.click(screen.getByRole("button", { name: /disparar Semana duplicada/ }));

    expect(screen.getByText("Serie agregada")).toBeInTheDocument();
    expect(screen.getByText("Semana duplicada")).toBeInTheDocument();

    // Cerrar uno cierra ése. Con una clave compartida —la hora, o un valor fijo—
    // los dos avisos son el mismo para React y para el filtro por id: se van los
    // dos juntos, y ver los dos textos en pantalla no lo delata.
    await userEvent.click(screen.getAllByRole("button", { name: /Cerrar el aviso/ })[0]!);
    expect(screen.queryByText("Serie agregada")).not.toBeInTheDocument();
    expect(screen.getByText("Semana duplicada")).toBeInTheDocument();
  });

  it("el mismo texto dos veces sale dos veces", async () => {
    // Apretar «Duplicar» dos veces son dos duplicaciones. Colapsarlas en un
    // aviso haría creer que la segunda no entró.
    montar();
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    expect(screen.getAllByText("Serie agregada")).toHaveLength(2);
  });

  it("el que falla se distingue por texto y no sólo por color", async () => {
    montar(<Boton texto="No se pudo guardar" tipo="mal" />);
    await userEvent.click(screen.getByRole("button", { name: /disparar/ }));
    // El color no llega ni al lector de pantalla ni a una pantalla con sol.
    expect(screen.getByText("No se pudo guardar")).toBeInTheDocument();
  });

  it("sin proveedor no revienta", () => {
    // Media docena de tests montan pedazos sueltos del editor. Que exploten por
    // no tener el proveedor sería cambiar «no se ve un aviso» por «no corre la
    // prueba».
    expect(() => render(<Boton texto="Suelto" />)).not.toThrow();
  });
});
