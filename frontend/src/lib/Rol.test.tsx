import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useApi } from "../api/useApi";
import { ProveedorDeRol, SelectorDeRol, useRol } from "./Rol";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

function Sonda() {
  const { rol } = useRol();
  const pedir = useApi();
  return (
    <>
      <SelectorDeRol />
      <span data-testid="rol">{rol}</span>
      <button type="button" onClick={() => void pedir("/api/athletes")}>
        pedir
      </button>
    </>
  );
}

/**
 * Este Node no expone `localStorage`, así que se le pone uno en memoria.
 *
 * Sin esto la persistencia no se puede verificar acá, y un test que no puede
 * fallar no dice nada. Con esto, "la elección sobrevive a recargar" prueba lo
 * que dice: que el valor se escribe y se vuelve a leer.
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

describe("el rol activo", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", almacenamientoFalso());
  });

  it("arranca en entrenador", () => {
    render(
      <ProveedorDeRol>
        <Sonda />
      </ProveedorDeRol>,
    );
    expect(screen.getByTestId("rol")).toHaveTextContent("coach");
  });

  it("el que se elige es el que viaja en Active-Role", async () => {
    // Es la razón de todo este contexto. Una persona puede ser entrenadora y
    // atleta de otro entrenador al mismo tiempo, y el backend se niega a
    // adivinar desde cuál está mirando.
    const pedido = vi.fn<typeof fetch>(() => Promise.resolve(new Response("[]", { status: 200 })));
    vi.stubGlobal("fetch", pedido);

    render(
      <ProveedorDeRol>
        <Sonda />
      </ProveedorDeRol>,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    await userEvent.click(screen.getByRole("button", { name: "pedir" }));

    const opciones = pedido.mock.calls[0]?.[1] ?? {};
    expect(new Headers(opciones.headers).get("Active-Role")).toBe("athlete");
  });

  it("la elección sobrevive a recargar", async () => {
    const { unmount } = render(
      <ProveedorDeRol>
        <Sonda />
      </ProveedorDeRol>,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    unmount();

    render(
      <ProveedorDeRol>
        <Sonda />
      </ProveedorDeRol>,
    );
    expect(screen.getByTestId("rol")).toHaveTextContent("athlete");
  });

  it("un valor basura guardado no rompe la aplicación", () => {
    // Nadie escribe esto a mano, pero una versión vieja pudo haber guardado otra
    // cosa y la aplicación entera cuelga del proveedor: acá un valor raro es una
    // pantalla en blanco, no un campo mal puesto.
    localStorage.setItem("rol-activo", "presidente");
    render(
      <ProveedorDeRol>
        <Sonda />
      </ProveedorDeRol>,
    );
    expect(screen.getByTestId("rol")).toHaveTextContent("coach");
  });

  it("sin proveedor falla nombrando el motivo", () => {
    // El default silencioso sería peor: un `coach` implícito es exactamente lo
    // que el backend se niega a asumir.
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Sonda />)).toThrow(/ProveedorDeRol/);
  });
});
