import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { SelectorDeRol } from "../lib/Rol";
import { montar } from "../lib/pruebas";
import { useAtletas } from "./consultas";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

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

/** Una sonda que pide sin forzar el rol, que es el caso donde la clave importa. */
function Sonda() {
  const { data } = useAtletas();
  return (
    <>
      <SelectorDeRol />
      <span data-testid="quien">{data?.[0]?.full_name ?? "…"}</span>
    </>
  );
}

function responderSegunElRol() {
  const pedido = vi.fn<typeof fetch>((_, opciones) => {
    const rol = new Headers(opciones?.headers).get("Active-Role");
    const nombre = rol === "athlete" ? "Mi ficha" : "Atleta de A";
    return Promise.resolve(
      new Response(JSON.stringify([{ id: "x", full_name: nombre, level: null }]), { status: 200 }),
    );
  });
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

describe("el rol es parte de la identidad de la consulta", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", almacenamientoFalso());
  });

  it("cambiar de rol no sirve lo que se cacheó con el otro", async () => {
    // La misma ruta contesta cosas distintas según quién pregunte. Si el rol no
    // entra en la clave, pasar a atleta reusa la respuesta del entrenador: la
    // pantalla no cambia y no sale ningún pedido nuevo. Es el bug que se vio
    // como "de atleta veo lo mismo que de entrenador".
    const pedido = responderSegunElRol();
    montar(<Sonda />);
    expect(await screen.findByText("Atleta de A")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    expect(await screen.findByText("Mi ficha")).toBeInTheDocument();
    expect(pedido).toHaveBeenCalledTimes(2);
  });

  it("y volver al primero tampoco trae el del segundo", async () => {
    responderSegunElRol();
    montar(<Sonda />);
    await screen.findByText("Atleta de A");
    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    await screen.findByText("Mi ficha");
    await userEvent.selectOptions(screen.getByRole("combobox"), "coach");
    expect(await screen.findByText("Atleta de A")).toBeInTheDocument();
  });

  it("el entrenador pide también los cerrados, el atleta no", async () => {
    // Dos preguntas distintas sobre la misma ruta: con quién trabajo hoy, y a
    // quién entrené alguna vez. Un vínculo pausado que no aparece en ninguna
    // lista queda sin forma de reanudarse.
    const pedido = responderSegunElRol();
    montar(<Sonda />);
    await screen.findByText("Atleta de A");
    await userEvent.selectOptions(screen.getByRole("combobox"), "athlete");
    await screen.findByText("Mi ficha");

    const rutas = (pedido as Mock<typeof fetch>).mock.calls.map(([u]) => String(u));
    expect(rutas[0]).toContain("incluir_cerrados=true");
    expect(rutas[1]).not.toContain("incluir_cerrados");
  });
});
