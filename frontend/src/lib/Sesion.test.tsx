import { render, screen } from "@testing-library/react";

import { ProveedorDeRol } from "./Rol";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Sesion } from "./Sesion";

/**
 * Clerk is faked at the module boundary, and only the part that decides.
 *
 * The alternative — standing up a real ClerkProvider — would test Clerk. What is
 * worth testing here is ours: that nothing which talks to the API is mounted
 * while there is no session. So `SignedIn` and `SignedOut` become switches this
 * file controls, and everything below them is the real code.
 */
const sesionIniciada = vi.hoisted(() => ({ valor: false }));

vi.mock("@clerk/clerk-react", () => ({
  SignedIn: ({ children }: { children: ReactNode }) => (sesionIniciada.valor ? children : null),
  SignedOut: ({ children }: { children: ReactNode }) => (sesionIniciada.valor ? null : children),
  SignIn: () => <div>Ingresar</div>,
  UserButton: () => <div>Cuenta</div>,
}));

/** Un hijo que pide datos al montarse, como lo hará el panel de verdad. */
function PideDatos() {
  void fetch("/api/athletes");
  return <p>datos</p>;
}

describe("la puerta de sesión", () => {
  beforeEach(() => {
    sesionIniciada.valor = false;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("[]"))));
  });

  it("sin sesión no llama al API ni una vez", () => {
    // La afirmación que importa, y se hace sobre los requests que salen y no
    // sobre lo que se ve. Una app que pide datos antes de tener token recibe 401
    // en cada carga, y eso le enseña a cualquiera que mire la consola que los
    // 401 de esta aplicación son normales.
    render(
      <ProveedorDeRol>
      <Sesion>
        <PideDatos />
      </Sesion>
      </ProveedorDeRol>,
    );

    expect(fetch).not.toHaveBeenCalled();
  });

  it("sin sesión muestra el ingreso y no el contenido", () => {
    render(
      <ProveedorDeRol>
      <Sesion>
        <PideDatos />
      </Sesion>
      </ProveedorDeRol>,
    );

    expect(screen.getByText("Ingresar")).toBeInTheDocument();
    expect(screen.queryByText("datos")).not.toBeInTheDocument();
  });

  it("con sesión sí monta el contenido", () => {
    // El control. Sin esto, una puerta que no deja pasar nunca pasaría los dos
    // tests de arriba y rompería la aplicación entera.
    sesionIniciada.valor = true;

    render(
      <ProveedorDeRol>
      <Sesion>
        <PideDatos />
      </Sesion>
      </ProveedorDeRol>,
    );

    expect(screen.getByText("datos")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
