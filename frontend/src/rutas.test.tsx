import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Rutas } from "./rutas";

/**
 * Entrar directo a una URL es lo mismo que recargar la página estando en ella:
 * la aplicación arranca de cero con esa dirección y tiene que llegar al mismo
 * lugar. Por eso `MemoryRouter` con `initialEntries` prueba lo que pide la
 * tarea sin necesitar un navegador.
 */
function en(ruta: string) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Rutas />
    </MemoryRouter>,
  );
}

describe("las rutas", () => {
  it("la raíz muestra el listado", () => {
    en("/");
    expect(screen.getByRole("heading", { name: "Atletas" })).toBeInTheDocument();
  });

  it("entrar directo al panel de un atleta llega a ese atleta", () => {
    // Lo que rompe si el atleta seleccionado vive en el estado de un componente
    // en vez de en la URL: recargar vuelve al principio, y el link que mandaste
    // por mensaje abre otra cosa.
    en("/atletas/abc-123");
    expect(screen.getByRole("heading", { name: "Panel de abc-123" })).toBeInTheDocument();
  });

  it("cada atleta tiene su propia dirección", () => {
    // El control. Sin esto, una ruta que ignore el parámetro pasaría el test de
    // arriba mostrando siempre el mismo panel.
    en("/atletas/otro-999");
    expect(screen.getByRole("heading", { name: "Panel de otro-999" })).toBeInTheDocument();
  });

  it("una dirección que no existe lo dice y ofrece volver", () => {
    en("/cualquier-cosa");
    expect(screen.getByRole("heading", { name: "Esa página no existe" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a los atletas" })).toBeInTheDocument();
  });
});
