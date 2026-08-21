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
    tiene_cuenta: true,
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
    tiene_cuenta: true,
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
    tiene_cuenta: false,
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

    expect(within(fichaDe("Lucía Paz")).getByText("hace 20 días").className).toMatch(/caida/);
    // Pedro hace 60 días, pero está pausado: no entrenar es lo esperado ahí.
    const pedro = within(fichaDe("Pedro Gil")).getByText(/2026|hace/);
    expect(pedro.className).not.toMatch(/caida/);
  });

  it("la semana del bloque sale sólo cuando hay bloque", async () => {
    // Dejó de ser una barra y pasó a ser texto: con veinte filas, veinte barras
    // de progreso compiten con la única que importa, que es la adherencia. El
    // número dice lo mismo y ocupa un renglón.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Martín Sosa" });

    expect(within(fichaDe("Martín Sosa")).getByText(/semana 3 de 4/)).toBeVisible();
    // Lucía no tiene bloque: no se le inventa uno.
    expect(within(fichaDe("Lucía Paz")).queryByText(/semana \d+ de/)).toBeNull();
  });
});

describe("el orden es por urgencia, no alfabético", () => {
  beforeEach(() => vi.unstubAllGlobals());

  const nombres = () =>
    screen.getAllByRole("link").map((e) => e.textContent).filter((n) => n !== "Armar la semana");

  it("primero el que no tiene programa, después el que se está cayendo", async () => {
    // La pregunta del domingo a la noche no es «¿dónde está Ana?» sino «¿a quién
    // le tengo que dar bola?». Alfabético contesta la primera, que ya la
    // contesta el buscador.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Ana Ruiz" });

    const orden = nombres();
    expect(orden.indexOf("Ana Ruiz")).toBeLessThan(orden.indexOf("Lucía Paz"));
    expect(orden.indexOf("Lucía Paz")).toBeLessThan(orden.indexOf("Martín Sosa"));
  });

  it("el pausado va al fondo aunque haga dos meses que no entrena", async () => {
    // No entrenar es exactamente lo que se espera de un vínculo pausado.
    // Ponerlo arriba sería una alarma sobre una decisión que ya tomó el
    // entrenador.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Pedro Gil" });

    const orden = nombres();
    expect(orden[orden.length - 1]).toBe("Pedro Gil");
  });

  it("cuenta en el encabezado cuántas piden atención", async () => {
    responder();
    montar(<ListadoDeAtletas />);
    expect(await screen.findByText(/piden atención/)).toBeVisible();
  });
});

describe("no tener cuenta es el caso normal", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("lo dice sin tratarlo como un problema", async () => {
    // El entrenador arma el programa entero antes de mandar el link. Si esto
    // apareciera como alerta, la pantalla estaría marcando como pendiente el
    // orden normal de trabajo.
    responder();
    montar(<ListadoDeAtletas />);
    await screen.findByRole("link", { name: "Ana Ruiz" });

    const ana = screen.getByRole("link", { name: "Ana Ruiz" }).closest("li")!;
    const chip = within(ana).getByText("Sin cuenta todavía");
    expect(chip).toBeVisible();
    expect(chip.className).not.toMatch(/alerta/);

    const martin = screen.getByRole("link", { name: "Martín Sosa" }).closest("li")!;
    expect(within(martin).queryByText("Sin cuenta todavía")).toBeNull();
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
