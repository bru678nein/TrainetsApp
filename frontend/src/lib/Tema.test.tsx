import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BotonDeTema, ProveedorDeTema } from "./Tema";

/**
 * El mismo `localStorage` en memoria que usa `Rol.test`: este Node no lo expone,
 * y sin él "la elección sobrevive a recargar" no se puede verificar.
 *
 * Se rearma en cada caso a propósito. Compartirlo hacía que el tema elegido en
 * un test decidiera el default del siguiente, que es una contaminación que sólo
 * aparece cuando alguien cambia el orden.
 */
function almacenamientoFalso(): Storage {
  const datos = new Map<string, string>();
  return {
    get length() {
      return datos.size;
    },
    clear: () => datos.clear(),
    getItem: (k) => datos.get(k) ?? null,
    key: (i) => [...datos.keys()][i] ?? null,
    removeItem: (k) => void datos.delete(k),
    setItem: (k, v) => void datos.set(k, v),
  };
}

const montar = () =>
  render(
    <ProveedorDeTema>
      <BotonDeTema />
    </ProveedorDeTema>,
  );

describe("el tema", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", almacenamientoFalso());
    delete document.documentElement.dataset.tema;
  });

  it("arranca en claro aunque el sistema esté en oscuro", () => {
    // La decisión que reemplazó a `prefers-color-scheme`: la aplicación se ve
    // igual en la máquina de cualquiera hasta que alguien elige otra cosa. Si
    // esto volviera a mirar el sistema, el default dejaría de ser el mismo para
    // todos y nadie se enteraría.
    montar();
    expect(document.documentElement.dataset.tema).toBe("claro");
  });

  it("el botón lleva al otro tema y lo dice", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Cambiar a modo oscuro" }));
    expect(document.documentElement.dataset.tema).toBe("oscuro");
    // Y ahora ofrece la vuelta: el nombre describe adónde va, no dónde está.
    expect(screen.getByRole("button", { name: "Cambiar a modo claro" })).toBeInTheDocument();
  });

  it("la elección sobrevive a recargar", async () => {
    const { unmount } = montar();
    await userEvent.click(screen.getByRole("button", { name: "Cambiar a modo oscuro" }));
    unmount();
    delete document.documentElement.dataset.tema;

    montar();
    expect(document.documentElement.dataset.tema).toBe("oscuro");
  });

  it("sin `localStorage` sigue andando en vez de romperse", async () => {
    // Modo privado de Safari: `setItem` tira. Perder la preferencia es aceptable;
    // que la aplicación no cargue, no.
    vi.stubGlobal("localStorage", {
      ...almacenamientoFalso(),
      getItem: () => {
        throw new Error("bloqueado");
      },
      setItem: () => {
        throw new Error("bloqueado");
      },
    });
    montar();
    expect(document.documentElement.dataset.tema).toBe("claro");
    await userEvent.click(screen.getByRole("button", { name: "Cambiar a modo oscuro" }));
    expect(document.documentElement.dataset.tema).toBe("oscuro");
  });
});
