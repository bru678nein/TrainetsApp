import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { montar } from "./lib/pruebas";
import { Rutas } from "./rutas";

// El listado consulta el API en cuanto se monta. Acá lo que se prueba son las
// rutas, así que la puerta al API se falsifica en el borde y devuelve vacío.
// Todos y no el último: el panel pide varias cosas al montarse, y quedarse con
// la última hace que el test dependa de cuál resuelve después.
const pedidos: string[] = [];
vi.mock("./api/useApi", () => ({
  useApi: () => (ruta: string) => {
    pedidos.push(ruta);
    return Promise.resolve([]);
  },
  // El panel monta formularios que escriben. Acá no se ejercitan: lo que se
  // prueba es a dónde llega cada dirección.
  useEnviar: () => () => Promise.resolve({}),
  useMutar: () => () => Promise.resolve({}),
}));

/**
 * Entrar directo a una URL es lo mismo que recargar la página estando en ella:
 * la aplicación arranca de cero con esa dirección y tiene que llegar al mismo
 * lugar. Por eso `MemoryRouter` con `initialEntries` prueba lo que pide la
 * tarea sin necesitar un navegador.
 */
function en(ruta: string) {
  return montar(<Rutas />, ruta);
}

describe("las rutas", () => {
  it("la raíz muestra el listado", async () => {
    en("/");
    expect(await screen.findByRole("heading", { name: "Atletas" })).toBeInTheDocument();
  });

  it("entrar directo al panel de un atleta llega a ese atleta", async () => {
    // Lo que rompe si el atleta seleccionado vive en el estado de un componente
    // en vez de en la URL: recargar vuelve al principio, y el link que mandaste
    // por mensaje abre otra cosa.
    en("/atletas/abc-123");
    expect(await screen.findByRole("tab", { name: "Rutina" })).toBeInTheDocument();
  });

  it("las gráficas son una pestaña más y no otra dirección", async () => {
    // Armar el bloque y mirar si se está cumpliendo son la misma conversación.
    // En dos direcciones distintas había que ir y volver para hacer una sola
    // cosa.
    en("/atletas/abc-123");
    await userEvent.click(await screen.findByRole("tab", { name: "Gráficas" }));
    expect(
      await screen.findByRole("heading", { name: "¿Está haciendo el trabajo?" }),
    ).toBeInTheDocument();
  });

  it("cada atleta tiene su propia dirección", async () => {
    // El control. Sin esto, una ruta que ignore el parámetro pasaría el test de
    // arriba mostrando siempre el mismo panel: el id llega desde la URL hasta la
    // consulta.
    en("/atletas/otro-999");
    await screen.findByRole("tab", { name: "Rutina" });
    expect(pedidos.some((r) => r.includes("otro-999"))).toBe(true);
  });

  it("una dirección que no existe lo dice y ofrece volver", () => {
    en("/cualquier-cosa");
    expect(screen.getByRole("heading", { name: "Esa página no existe" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a los atletas" })).toBeInTheDocument();
  });
});
