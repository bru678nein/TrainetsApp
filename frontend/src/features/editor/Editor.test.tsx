import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Editor } from "./Editor";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const PROGRAMA = { id: "p1", name: "Programa", starts_on: null };
const MESO = {
  id: "m1",
  ordinal: 1,
  label: "Acumulación",
  week_count: 4,
  focus: null,
  rir_progression: [0, 0, -1, -1],
};
/** Sólo las semanas 1 y 2 están armadas: la 3 y la 4 quedan vacías a propósito. */
const AGENDA = [
  { id: "s1", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 1 },
  { id: "s2", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 2 },
  { id: "s3", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 2, day_number: 1 },
];

/**
 * El orden de estas condiciones importa y por eso están de la más específica a
 * la más general: `/api/programs/p1/mesocycles` contiene `/programs`, así que
 * preguntar por el prefijo corto primero devuelve la lista equivocada y el
 * editor se queda sin bloques sin decir por qué.
 */
function cuerpoPara(url: string): unknown {
  if (url.includes("/mesocycles")) return [MESO];
  if (url.includes("/programs")) return [PROGRAMA];
  if (url.match(/\/api\/sessions\//)) {
    return { id: "s1", mesocycle: "Acumulación", week_number: 1, day_number: 1, blocks: [] };
  }
  if (url.includes("/sessions")) return AGENDA;
  return [];
}

function responder() {
  const pedido = vi.fn<typeof fetch>((url) =>
    Promise.resolve(new Response(JSON.stringify(cuerpoPara(String(url))), { status: 200 })),
  );
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

function montarEditor() {
  return montar(
    <Routes>
      <Route path="/atletas/:atletaId/programa" element={<Editor />} />
    </Routes>,
    "/atletas/a1/programa",
  );
}

describe("las semanas del bloque", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("dibuja todas las del mesociclo, no sólo las que tienen sesiones", async () => {
    // Es lo que hace visible que la 3 no está armada. En una lista de lo que
    // hay, lo que falta no ocupa lugar y no se ve.
    responder();
    montarEditor();
    for (const n of [1, 2, 3, 4]) {
      expect(await screen.findByRole("heading", { name: `Semana ${n}` })).toBeInTheDocument();
    }
  });

  it("una semana sin sesiones lo dice, en vez de quedar en blanco", async () => {
    responder();
    montarEditor();
    expect(await screen.findAllByText("Sin sesiones")).toHaveLength(2);
  });

  it("cada sesión de la semana queda bajo su panel", async () => {
    responder();
    montarEditor();
    const semana1 = (await screen.findByRole("heading", { name: "Semana 1" })).closest("section")!;
    const semana2 = (await screen.findByRole("heading", { name: "Semana 2" })).closest("section")!;
    expect(semana1.querySelectorAll("button[aria-expanded]")).toHaveLength(2);
    expect(semana2.querySelectorAll("button[aria-expanded]")).toHaveLength(1);
  });
});

describe("abrir una sesión", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("arranca cerrada y se abre al apretarla", async () => {
    // `aria-expanded` no es sólo para el lector: la flecha gira desde ese
    // atributo, así que el estado que se anuncia y el que se dibuja son el
    // mismo. Dos fuentes se desincronizan.
    responder();
    montarEditor();
    const boton = (await screen.findAllByRole("button", { name: /Día 1/ }))[0]!;
    expect(boton).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(boton);
    expect(boton).toHaveAttribute("aria-expanded", "true");
  });

  it("abrir una cierra la anterior", async () => {
    // El contenido de una sesión es largo. Con dos abiertas hay que hacer scroll
    // para comparar lo que la rejilla acababa de poner al lado.
    responder();
    montarEditor();
    const botones = await screen.findAllByRole("button", { name: /Día/ });
    await userEvent.click(botones[0]!);
    await userEvent.click(botones[1]!);

    expect(botones[0]).toHaveAttribute("aria-expanded", "false");
    expect(botones[1]).toHaveAttribute("aria-expanded", "true");
  });
});

describe("agregar y borrar días", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("el + de cada panel propone el primer día libre de esa semana", async () => {
    // La semana 1 tiene los días 1 y 2, así que le toca el 3; la 2 tiene el 1,
    // así que le toca el 2. El número sale del panel y no de un formulario
    // suelto que hay que completar dos veces.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    expect(screen.getByTitle("Agregar el día 3")).toBeInTheDocument();
    expect(screen.getByTitle("Agregar el día 2")).toBeInTheDocument();
  });

  it("apretarlo crea la sesión en esa semana y ese día", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    await userEvent.click(screen.getByTitle("Agregar el día 3"));

    const alta = pedido.mock.calls.find(
      ([, o]) => o?.method === "POST" && String(o?.body).includes("week_number"),
    );
    expect(alta).toBeDefined();
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ week_number: 1, day_number: 3 });
  });

  it("una semana llena lo dice, en vez de ofrecer un botón que falla", async () => {
    // Siete días es el tope de la semana. Un `+` que contesta 409 promete algo
    // que no puede cumplir.
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const u = String(url);
        if (u.includes("/mesocycles")) return Promise.resolve(new Response(JSON.stringify([MESO])));
        if (u.includes("/programs")) return Promise.resolve(new Response(JSON.stringify([PROGRAMA])));
        if (u.match(/\/api\/sessions\//)) return Promise.resolve(new Response(JSON.stringify({})));
        if (u.includes("/sessions")) {
          const llena = [1, 2, 3, 4, 5, 6, 7].map((d) => ({
            id: `s${d}`,
            mesocycle: "Acumulación",
            mesocycle_ordinal: 1,
            week_number: 1,
            day_number: d,
          }));
          return Promise.resolve(new Response(JSON.stringify(llena)));
        }
        return Promise.resolve(new Response("[]"));
      }),
    );
    montarEditor();
    expect(await screen.findByText("Semana completa")).toBeInTheDocument();
    expect(screen.getByTitle("Esta semana ya tiene los siete días")).toBeDisabled();
  });

  it("cada día tiene su propio botón de borrar, nombrado", async () => {
    // El nombre accesible dice cuál se borra. «🗑» a secas se anuncia igual en
    // los tres días de la semana, y borrar no tiene deshacer.
    responder();
    montarEditor();
    expect(
      await screen.findByRole("button", { name: "Borrar el día 1 de la semana 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Borrar el día 2 de la semana 1" }),
    ).toBeInTheDocument();
  });

  it("borrar el día abierto lo cierra antes de sacarlo", async () => {
    // Si no, queda montado el contenido de una sesión que ya no existe y su
    // consulta contesta 404 sobre una pantalla que la persona no está mirando.
    responder();
    montarEditor();
    const dia = (await screen.findAllByRole("button", { name: /Día 1/ }))[0]!;
    await userEvent.click(dia);
    expect(dia).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(screen.getByRole("button", { name: "Borrar el día 1 de la semana 1" }));
    expect(dia).toHaveAttribute("aria-expanded", "false");
  });
});

describe("las dos pestañas del editor", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("arranca en mesociclos", async () => {
    responder();
    montarEditor();
    expect(await screen.findByRole("heading", { name: "Semana 1" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Crear un ejercicio" })).not.toBeInTheDocument();
  });

  it("el catálogo vive en su propia pestaña", async () => {
    // Armar el bloque de este atleta y mantener el catálogo son cosas distintas:
    // el catálogo es del entrenador y lo comparten todos sus atletas. Juntas,
    // parecía que crear un ejercicio era parte de armar este programa.
    responder();
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));

    expect(screen.getByRole("heading", { name: "Crear un ejercicio" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Semana 1" })).not.toBeInTheDocument();
  });

  it("el patrón de movimiento se elige del catálogo que manda el API", async () => {
    // Ni una lista escrita a mano ni un texto libre: son once filas cerradas, y
    // que sean cerradas es lo que hace contestable la pregunta por volumen.
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const u = String(url);
        if (u.includes("movement-patterns")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { code: "rodilla_dominante", label_es: "Rodilla dominante" },
                { code: "pliometria", label_es: "PLIOMETRIA" },
              ]),
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify(cuerpoPara(u))));
      }),
    );
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));

    const patron = await screen.findByLabelText("Patrón de movimiento");
    expect([...patron.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
      "— patrón de movimiento —",
      "Rodilla dominante",
      "PLIOMETRIA",
    ]);
  });
});
