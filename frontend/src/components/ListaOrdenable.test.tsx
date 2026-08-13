import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ListaOrdenable } from "./ListaOrdenable";

const TRES = [
  { id: "a", nombre: "Sentadilla" },
  { id: "b", nombre: "Press banca" },
  { id: "c", nombre: "Remo" },
];

function montarLista(onOrdenar = vi.fn()) {
  render(
    <ListaOrdenable elementos={TRES} onOrdenar={onOrdenar}>
      {(e) => <span>{e.nombre}</span>}
    </ListaOrdenable>,
  );
  return onOrdenar;
}

/**
 * La secuencia de arrastre, disparada a mano.
 *
 * Sin `DataTransfer`, que jsdom no implementa — y no hace falta: el componente
 * lleva qué se agarró en estado de React en vez de meterlo en el portapapeles
 * del arrastre, justamente porque así es testeable sin un navegador.
 */
function arrastrar(desde: HTMLElement, hasta: HTMLElement) {
  fireEvent.dragStart(desde);
  fireEvent.dragOver(hasta);
  fireEvent.drop(hasta);
}

describe("reordenar arrastrando", () => {
  it("soltar sobre otro manda la lista completa en el orden nuevo", () => {
    // La lista entera y no un movimiento: hace la operación idempotente y deja
    // que el servidor verifique que están todos. Un "movete a la 3" obliga al
    // cliente a saber qué había en 3, y dos pestañas lo saben distinto.
    const onOrdenar = montarLista();
    const filas = screen.getAllByRole("listitem");
    arrastrar(filas[0]!, filas[2]!);
    expect(onOrdenar).toHaveBeenCalledWith(["b", "c", "a"]);
  });

  it("soltar sobre sí mismo no manda nada", () => {
    const onOrdenar = montarLista();
    const filas = screen.getAllByRole("listitem");
    arrastrar(filas[1]!, filas[1]!);
    expect(onOrdenar).not.toHaveBeenCalled();
  });
});

describe("reordenar sin arrastrar", () => {
  it("bajar el primero lo intercambia con el segundo", async () => {
    // Arrastrar es un gesto que mucha gente no puede hacer, y no sólo quien usa
    // teclado. Si el orden sólo se cambiara arrastrando, para esas personas el
    // orden no se podría cambiar.
    const onOrdenar = montarLista();
    await userEvent.click(screen.getAllByRole("button", { name: /Bajar/ })[0]!);
    expect(onOrdenar).toHaveBeenCalledWith(["b", "a", "c"]);
  });

  it("subir el último lo intercambia con el anterior", async () => {
    const onOrdenar = montarLista();
    const subir = screen.getAllByRole("button", { name: /Subir/ });
    await userEvent.click(subir[subir.length - 1]!);
    expect(onOrdenar).toHaveBeenCalledWith(["a", "c", "b"]);
  });

  it("los extremos no ofrecen salir de la lista", () => {
    montarLista();
    expect(screen.getAllByRole("button", { name: /Subir/ })[0]).toBeDisabled();
    const bajar = screen.getAllByRole("button", { name: /Bajar/ });
    expect(bajar[bajar.length - 1]).toBeDisabled();
  });

  it("mientras se está guardando no se puede volver a mover", () => {
    // Dos reordenados en vuelo se pisan: el segundo sale de una lista que el
    // primero todavía no confirmó, y gana el que llegue último.
    render(
      <ListaOrdenable elementos={TRES} onOrdenar={vi.fn()} deshabilitado>
        {(e) => <span>{e.nombre}</span>}
      </ListaOrdenable>,
    );
    for (const boton of screen.getAllByRole("button")) expect(boton).toBeDisabled();
  });
});
