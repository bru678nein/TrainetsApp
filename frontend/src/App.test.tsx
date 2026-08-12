import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./api/useApi", () => ({
  useApi: () => () => Promise.resolve([]),
  useEnviar: () => () => Promise.resolve({}),
}));

/**
 * Lo que este archivo verifica es la **composición**: que las rutas cuelguen de
 * la puerta de sesión y no al lado.
 *
 * Puestas afuera, la aplicación entera renderiza para cualquiera que abra la
 * URL. Se vería casi igual —los datos no llegarían— pero la estructura del panel,
 * los nombres de las secciones y la forma del programa sí. Y el error se comete
 * moviendo un componente dos líneas.
 */
const sesionIniciada = vi.hoisted(() => ({ valor: false }));

vi.mock("@clerk/clerk-react", () => ({
  SignedIn: ({ children }: { children: ReactNode }) => (sesionIniciada.valor ? children : null),
  SignedOut: ({ children }: { children: ReactNode }) => (sesionIniciada.valor ? null : children),
  SignIn: () => <div>Ingresar</div>,
  UserButton: () => <div>Cuenta</div>,
}));

describe("la carcasa", () => {
  beforeEach(() => {
    sesionIniciada.valor = false;
  });

  it("sin sesión no renderiza ninguna ruta", () => {
    render(<App />);
    expect(screen.getByText("Ingresar")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Atletas" })).not.toBeInTheDocument();
  });

  it("con sesión sí", async () => {
    // El control: sin esto, una puerta que no deja pasar nunca pasaría el test
    // de arriba y la aplicación no serviría para nada.
    sesionIniciada.valor = true;
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Atletas" })).toBeInTheDocument();
  });
});
