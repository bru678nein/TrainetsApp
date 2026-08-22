import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { SelectorDeRol } from "../lib/Rol";
import { montar } from "../lib/pruebas";
import { Inicio } from "./Inicio";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const COMO_ENTRENADOR = [{ id: "a1", full_name: "Atleta de A", level: null, estado: "activo" }];
const COMO_ATLETA = [{ id: "a9", full_name: "Mi ficha", level: null, estado: "activo" }];

/** Contesta distinto según el rol que traiga la cabecera, como el backend. */
function responderSegunElRol() {
  const pedido = vi.fn<typeof fetch>((url, opciones) => {
    const rol = new Headers(opciones?.headers).get("Active-Role");
    const cuerpo = String(url).includes("/sessions")
      ? []
      : rol === "athlete"
        ? COMO_ATLETA
        : COMO_ENTRENADOR;
    return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
  });
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

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

/**
 * Con qué rol se pidió **el listado de fichas**, que es la consulta de la que
 * habla este archivo.
 *
 * Acotado a esa ruta y no a todos los pedidos: la pantalla hace más de uno —el
 * espacio del entrenador, por ejemplo— y contarlos todos hace que este caso se
 * rompa cada vez que alguien agrega una consulta, diciendo que el rol falló
 * cuando lo que cambió fue otra cosa.
 */
function rolesPedidos(pedido: Mock<typeof fetch>): string[] {
  return pedido.mock.calls
    .filter(([u]) => new URL(String(u), "http://x").pathname === "/api/athletes")
    .map(([, o]) => new Headers(o?.headers).get("Active-Role") ?? "");
}

describe("la pantalla de entrada depende del rol", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", almacenamientoFalso());
  });

  it("como entrenador es el listado de atletas, con sus acciones", async () => {
    responderSegunElRol();
    montar(<Inicio />);
    expect(await screen.findByRole("heading", { name: "Atletas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agregar" })).toBeInTheDocument();
  });

  it("como atleta NO ofrece las acciones del entrenador", async () => {
    // Un botón que la base va a rechazar es peor que un botón que no está:
    // promete algo y falla recién cuando alguien confía.
    responderSegunElRol();
    montar(
      <>
        <SelectorDeRol />
        <Inicio />
      </>,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");

    expect(screen.queryByRole("button", { name: "Agregar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "archivar" })).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Mis sesiones" })).toBeInTheDocument();
  });

  it("cambiar de rol vuelve a preguntar, en vez de servir lo cacheado", async () => {
    // El bug que este archivo viene a fijar. La clave de la consulta no incluía
    // el rol efectivo, así que pasar a atleta reusaba la respuesta del
    // entrenador: la misma ruta contesta cosas distintas según quién pregunte, y
    // el rol es parte de la identidad de la consulta y no un detalle del pedido.
    const pedido = responderSegunElRol();
    montar(
      <>
        <SelectorDeRol />
        <Inicio />
      </>,
    );
    await screen.findByText("Atleta de A");

    expect(rolesPedidos(pedido)).toEqual(["coach"]);

    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    await screen.findByRole("heading", { name: "Mis sesiones" });

    // Lo que se mira es que haya salido un pedido *como atleta*. El nombre de la
    // ficha no sirve de testigo: la pantalla del atleta muestra sus sesiones, no
    // sus fichas, así que buscarlo pasaría por el motivo equivocado.
    expect(rolesPedidos(pedido)).toContain("athlete");
    expect(screen.queryByText("Atleta de A")).not.toBeInTheDocument();
  });
});
