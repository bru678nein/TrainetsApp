import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { ListadoDeAtletas } from "./ListadoDeAtletas";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const haceDias = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

const ATLETAS = [
  {
    id: "a1",
    full_name: "Martín Sosa",
    level: null,
    estado: "activo",
    ultima_sesion: haceDias(2),
    programa_actual: "Fuerza general",
    semana_actual: 3,
    semanas_del_bloque: 4,
  },
  {
    id: "a2",
    full_name: "Lucía Paz",
    level: null,
    estado: "activo",
    ultima_sesion: haceDias(20),
    programa_actual: "Hipertrofia",
    semana_actual: null,
    semanas_del_bloque: null,
  },
  {
    id: "a3",
    full_name: "Pedro Gil",
    level: null,
    estado: "pausado",
    ultima_sesion: haceDias(60),
    programa_actual: null,
    semana_actual: null,
    semanas_del_bloque: null,
  },
  {
    id: "a4",
    full_name: "Ana Ruiz",
    level: null,
    estado: "activo",
    ultima_sesion: null,
    programa_actual: null,
    semana_actual: null,
    semanas_del_bloque: null,
  },
];

function responder() {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response(JSON.stringify(ATLETAS), { status: 200 })),
    ),
  );
}

const fichaDe = (nombre: string) => screen.getByRole("link", { name: nombre }).closest("li")!;

describe("el listado dice quién se está cayendo", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("cada ficha trae hace cuánto entrenó, sin abrirla", async () => {
    // Es el dato por el que existe esta pantalla: lo que una planilla no puede
    // contestar sola. El nombre y el estado el entrenador ya los sabe.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Martín Sosa" });

    expect(within(fichaDe("Martín Sosa")).getByText("hace 2 días")).toBeVisible();
    expect(within(fichaDe("Ana Ruiz")).getByText("nunca")).toBeVisible();
  });

  it("nunca entrenó no se dibuja como abandono", async () => {
    // Una ficha recién cargada no es alguien que se fue. Marcarla en rojo le
    // pone al entrenador un problema que no tiene.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Ana Ruiz" });

    expect(within(fichaDe("Ana Ruiz")).getByText("nunca").className).not.toMatch(/alerta/);
  });

  it("dos semanas sin entrenar se marcan, y sólo en los activos", async () => {
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Lucía Paz" });

    expect(within(fichaDe("Lucía Paz")).getByText("hace 20 días").className).toMatch(/alerta/);
    // Pedro hace 60 días, pero está pausado: no entrenar es lo esperado ahí.
    const pedro = within(fichaDe("Pedro Gil")).getByText(/2026|hace/);
    expect(pedro.className).not.toMatch(/alerta/);
  });

  it("el progreso del bloque sale sólo cuando hay bloque", async () => {
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Martín Sosa" });

    expect(within(fichaDe("Martín Sosa")).getByText("3 de 4")).toBeVisible();
    expect(within(fichaDe("Lucía Paz")).queryByRole("progressbar")).toBeNull();
  });
});

describe("buscar y filtrar", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("busca por nombre, sin acentos", async () => {
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Martín Sosa" });

    await userEvent.type(screen.getByLabelText("Buscar atletas"), "martin");
    expect(screen.getByRole("link", { name: "Martín Sosa" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Lucía Paz" })).toBeNull();
  });

  it("busca también por programa", async () => {
    // El entrenador piensa en bloques: «¿quiénes están en hipertrofia?» es una
    // pregunta que se hace, y el nombre del atleta no la contesta.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Lucía Paz" });

    await userEvent.type(screen.getByLabelText("Buscar atletas"), "hipertrofia");
    expect(screen.getByRole("link", { name: "Lucía Paz" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Martín Sosa" })).toBeNull();
  });

  it("el filtro de estado deja sólo ese estado", async () => {
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Pedro Gil" });

    await userEvent.click(screen.getByRole("button", { name: "Pausados" }));
    expect(screen.getByRole("link", { name: "Pedro Gil" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Martín Sosa" })).toBeNull();
  });

  it("sin coincidencias no dice que no cargaste ninguno", async () => {
    // Hay atletas y el filtro los esconde. «Todavía no cargaste ninguno» sería
    // mentir sobre lo que está pasando.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Martín Sosa" });

    await userEvent.type(screen.getByLabelText("Buscar atletas"), "zzzz");
    expect(screen.getByText(/Ningún atleta coincide/)).toBeVisible();
    expect(screen.queryByText(/Todavía no cargaste/)).toBeNull();
  });
});
