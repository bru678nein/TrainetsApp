import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Selector } from "./Selector";

describe("elegir un número de una lista corta", () => {
  it("ofrece todas las opciones del rango", () => {
    render(<Selector etiqueta="Día" valor={1} onCambio={vi.fn()} max={7} />);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
      "7",
    ]);
  });

  it("es un desplegable nativo y no un menú propio", () => {
    // Es la decisión entera. En el celular abre la rueda del sistema, el gesto
    // que la persona ya conoce; el teclado funciona sin escribir nada; y no hay
    // que resolver a mano foco atrapado, Escape, ni salirse de la pantalla.
    render(<Selector etiqueta="Día" valor={1} onCambio={vi.fn()} max={7} />);
    expect(screen.getByRole("combobox").tagName).toBe("SELECT");
  });

  it("elegir avisa con el número y no con el evento", async () => {
    const onCambio = vi.fn();
    render(<Selector etiqueta="Día" valor={1} onCambio={onCambio} max={7} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "5");
    expect(onCambio).toHaveBeenCalledWith(5);
  });

  it("la etiqueta está asociada al control", () => {
    // Hay dos en la misma fila —«de la» y «a la»— y sin esto un lector de
    // pantalla los anuncia igual.
    render(<Selector etiqueta="Semana" valor={1} onCambio={vi.fn()} max={4} />);
    expect(screen.getByLabelText("Semana")).toBeInTheDocument();
  });

  it("muestra el valor elegido, no el primero de la lista", () => {
    render(<Selector etiqueta="Semana" valor={3} onCambio={vi.fn()} max={4} />);
    expect(screen.getByRole<HTMLSelectElement>("combobox").value).toBe("3");
  });

  it("con una sola opción no dibuja un desplegable", () => {
    // Un mesociclo de una semana no tiene "qué semana", y un desplegable de un
    // elemento pide que lo abran para no ofrecer nada.
    render(<Selector etiqueta="Semana" valor={1} onCambio={vi.fn()} max={1} />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Semana")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });
});
