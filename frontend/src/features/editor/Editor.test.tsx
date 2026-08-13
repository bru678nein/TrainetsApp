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
