import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { montar } from "./lib/pruebas";
import { Rutas } from "./rutas";

// El listado consulta el API en cuanto se monta. Acá lo que se prueba son las
// rutas, así que la puerta al API se falsifica en el borde y devuelve vacío.
let pedido = "";
vi.mock("./api/useApi", () => ({
  useApi: () => (ruta: string) => {
    pedido = ruta;
    return Promise.resolve([]);
  },
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
    expect(await screen.findByRole("heading", { name: "Adherencia por patrón" })).toBeInTheDocument();
  });

  it("cada atleta tiene su propia dirección", async () => {
    // El control. Sin esto, una ruta que ignore el parámetro pasaría el test de
    // arriba mostrando siempre el mismo panel.
    // El id llega desde la URL hasta la consulta: sin eso, el panel de cualquier
    // atleta mostraría los datos del mismo.
    en("/atletas/otro-999");
    await screen.findByRole("heading", { name: "Adherencia por patrón" });
    expect(pedido).toContain("otro-999");
  });

  it("una dirección que no existe lo dice y ofrece volver", () => {
    en("/cualquier-cosa");
    expect(screen.getByRole("heading", { name: "Esa página no existe" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a los atletas" })).toBeInTheDocument();
  });
});
