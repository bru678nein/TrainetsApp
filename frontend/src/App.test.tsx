import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

// Clerk necesita su proveedor para montar. Acá se lo falsifica al mínimo porque
// lo que este archivo verifica es el andamiaje —que TypeScript, React, jsdom y
// Testing Library estén conectados de verdad—, no la sesión. Eso vive en
// `lib/Sesion.test.tsx`, que sí controla los dos estados.
vi.mock("@clerk/clerk-react", () => ({
  SignedIn: () => null,
  SignedOut: ({ children }: { children: ReactNode }) => children,
  SignIn: () => <div>Ingresar</div>,
  UserButton: () => null,
}));

describe("el andamiaje", () => {
  it("renderiza, o sea que la cadena entera funciona", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "AppWeb Lean" })).toBeInTheDocument();
  });
});
