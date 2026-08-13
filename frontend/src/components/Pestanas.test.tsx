import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Pestanas } from "./Pestanas";

const DOS = [
  { id: "a", titulo: "Mesociclos", contenido: <p>los bloques</p> },
  { id: "b", titulo: "Ejercicios", contenido: <p>el catálogo</p> },
];

const pestana = (nombre: string) => screen.getByRole("tab", { name: nombre });

describe("elegir una pestaña", () => {
  it("arranca en la primera y muestra sólo su contenido", () => {
    render(<Pestanas pestanas={DOS} />);
    expect(pestana("Mesociclos")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("los bloques")).toBeInTheDocument();
    expect(screen.queryByText("el catálogo")).not.toBeInTheDocument();
  });

  it("apretar otra la cambia", async () => {
    render(<Pestanas pestanas={DOS} />);
    await userEvent.click(pestana("Ejercicios"));
    expect(screen.getByText("el catálogo")).toBeInTheDocument();
    expect(screen.queryByText("los bloques")).not.toBeInTheDocument();
  });

  it("el panel dice de qué pestaña es", () => {
    // Sin `aria-controls` y `aria-labelledby`, un lector anuncia una región
    // suelta y no puede decir a cuál de las dos pertenece.
    render(<Pestanas pestanas={DOS} />);
    const panel = screen.getByRole("tabpanel");
    expect(pestana("Mesociclos")).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", pestana("Mesociclos").id);
  });
});

describe("el teclado, que es lo que las hace pestañas", () => {
  it("Tab entra una sola vez al grupo, no una por pestaña", async () => {
    // La diferencia con una lista de botones. Son una sola elección: Tab entra y
    // sale del grupo entero, y adentro se mueve con las flechas. Una
    // implementación a medias se ve igual y se comporta distinto, que es peor
    // que no tenerla.
    render(<Pestanas pestanas={DOS} />);
    expect(pestana("Mesociclos")).toHaveAttribute("tabindex", "0");
    expect(pestana("Ejercicios")).toHaveAttribute("tabindex", "-1");
  });

  it("la flecha derecha pasa a la siguiente y se lleva el foco", async () => {
    render(<Pestanas pestanas={DOS} />);
    pestana("Mesociclos").focus();
    await userEvent.keyboard("{ArrowRight}");

    expect(pestana("Ejercicios")).toHaveAttribute("aria-selected", "true");
    // El foco sigue a la selección: si se quedara atrás, la flecha siguiente
    // partiría de donde está el foco y no de lo que la persona ve elegido.
    expect(document.activeElement).toBe(pestana("Ejercicios"));
  });

  it("la flecha izquierda desde la primera da la vuelta", async () => {
    render(<Pestanas pestanas={DOS} />);
    pestana("Mesociclos").focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(pestana("Ejercicios")).toHaveAttribute("aria-selected", "true");
  });

  it("Inicio y Fin van a los extremos", async () => {
    render(<Pestanas pestanas={DOS} />);
    pestana("Mesociclos").focus();
    await userEvent.keyboard("{End}");
    expect(pestana("Ejercicios")).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Home}");
    expect(pestana("Mesociclos")).toHaveAttribute("aria-selected", "true");
  });
});
