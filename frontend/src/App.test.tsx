import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("el andamiaje", () => {
  it("renderiza, o sea que la cadena entera funciona", () => {
    // No verifica nada del producto: verifica que TypeScript, React, jsdom y
    // Testing Library estén realmente conectados. Sin esta afirmación, una suite
    // vacía pasa igual y el andamiaje parece bueno hasta el primer test de verdad.
    render(<App />);
    expect(screen.getByRole("heading", { name: "AppWeb Lean" })).toBeInTheDocument();
  });
});
