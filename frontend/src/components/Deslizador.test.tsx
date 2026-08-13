import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Deslizador } from "./Deslizador";

describe("elegir entre pocos números", () => {
  it("muestra el valor, que un rango pelado no muestra", () => {
    // Un rango sin número es una posición sin dato: se ve dónde está el pulgar y
    // no qué eligió.
    render(<Deslizador etiqueta="Día" valor={3} onCambio={vi.fn()} max={7} />);
    expect(screen.getByRole("status")).toHaveTextContent("3");
  });

  it("muestra los extremos, que es lo que hay que saber para elegir", () => {
    // Sin ellos no se distingue un bloque de cuatro semanas de uno de dieciséis.
    render(<Deslizador etiqueta="Semana" valor={2} onCambio={vi.fn()} max={16} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("16")).toBeInTheDocument();
  });

  it("el rango va de 1 al máximo", () => {
    render(<Deslizador etiqueta="Día" valor={1} onCambio={vi.fn()} max={7} />);
    const control = screen.getByRole("slider");
    expect(control).toHaveAttribute("min", "1");
    expect(control).toHaveAttribute("max", "7");
  });

  it("la etiqueta está asociada al control", () => {
    // Sin esto un lector de pantalla anuncia "control deslizante" y nada más:
    // hay dos en la misma fila y no se distinguen.
    render(<Deslizador etiqueta="Semana" valor={1} onCambio={vi.fn()} max={4} />);
    expect(screen.getByLabelText("Semana")).toBeInTheDocument();
  });

  it("mover el control avisa con el número, no con el evento", () => {
    const onCambio = vi.fn();
    render(<Deslizador etiqueta="Día" valor={1} onCambio={onCambio} max={7} />);
    // El teclado ya funciona solo en un `input type=range` —flechas, Inicio,
    // Fin—: por eso esto no necesita el par de botones que sí necesita reordenar
    // arrastrando.
    fireEvent.change(screen.getByRole("slider"), { target: { value: "5" } });
    expect(onCambio).toHaveBeenCalledWith(5);
  });

  it("con un solo valor posible no ofrece un control muerto", () => {
    // Un mesociclo de una semana no tiene "qué semana". Un rango que no se puede
    // mover invita a intentarlo.
    render(<Deslizador etiqueta="Semana" valor={1} onCambio={vi.fn()} max={1} />);
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.getByText("Semana")).toBeInTheDocument();
  });
});
