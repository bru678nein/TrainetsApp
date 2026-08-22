import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { ListadoDeAtletas } from "./ListadoDeAtletas";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const IMPORTADO = {
  athlete_id: "a9",
  athlete_name: "Planilla de prueba",
  creados: { mesocycles: 5, prescribed_sets: 1345, exercises: 60 },
  revisar: ["S3 D1 Sentadilla trasera"],
};

/** El listado vacío, y un espacio que dice si la beta está habilitada. */
function responder(puedeImportar: boolean) {
  const pedido = vi.fn<typeof fetch>((url, opciones) => {
    const u = String(url);
    const cuerpo = u.includes("/api/coach")
      ? { id: "c1", display_name: "Yo", athlete_count: 0, puede_importar: puedeImportar }
      : u.includes("/import") && opciones?.method === "POST"
        ? IMPORTADO
        : [];
    return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
  });
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

const archivo = () =>
  new File(["x"], "planilla.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

describe("importar una planilla", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("sin la bandera no se ofrece", async () => {
    // Está en prueba con un entrenador. Un botón que contesta 403 es peor que
    // uno que no está: quien lo aprieta descubre que no puede y no hay nada que
    // pueda hacer al respecto.
    responder(false);
    montar(<ListadoDeAtletas />);
    await screen.findByRole("heading", { name: "Atletas" });
    expect(screen.queryByText(/Importar desde Excel/)).toBeNull();
  });

  it("con la bandera aparece al lado del alta a mano", async () => {
    responder(true);
    montar(<ListadoDeAtletas />);
    expect(await screen.findByText("Importar desde Excel")).toBeVisible();
    // Y sigue estando la otra forma de empezar: son alternativas, no reemplazo.
    expect(screen.getByRole("button", { name: "Agregar" })).toBeVisible();
  });

  it("sube el archivo como multipart y no como JSON", async () => {
    // Serializado a JSON el archivo llega como `{}`. Y el `Content-Type` no se
    // pone a mano: el navegador tiene que agregarle el `boundary`.
    const pedido = responder(true);
    montar(<ListadoDeAtletas />);
    await screen.findByText("Importar desde Excel");

    await userEvent.upload(screen.getByLabelText(/Importar desde Excel/), archivo());
    await screen.findByText(/Se creó/);

    const subida = pedido.mock.calls.find(([u]) => String(u).includes("/import"));
    expect(subida).toBeDefined();
    expect(subida![1]!.body).toBeInstanceOf(FormData);
    const cabeceras = subida![1]!.headers as Record<string, string>;
    expect(cabeceras["Content-Type"]).toBeUndefined();
  });

  it("cuenta lo que dejó y muestra lo que hay que revisar", async () => {
    // Lo de revisar no es una lista de errores: es lo que el parseo no pudo
    // desambiguar y dejó vacío en vez de inventar. Esconderlo sería dejar huecos
    // silenciosos en el programa.
    responder(true);
    montar(<ListadoDeAtletas />);
    await screen.findByText("Importar desde Excel");

    await userEvent.upload(screen.getByLabelText(/Importar desde Excel/), archivo());
    expect(await screen.findByText("Planilla de prueba")).toBeVisible();
    expect(screen.getByText("1345")).toBeVisible();
    expect(screen.getByText(/quedaron sin repeticiones/)).toBeVisible();
  });
});
