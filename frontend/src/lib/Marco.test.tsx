import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "./pruebas";
import { Marco } from "./Marco";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
  UserButton: () => <button type="button">Cuenta</button>,
}));

/**
 * El encabezado es lo que se ve en todas las pantallas, y su navegación cambia
 * con el rol: un atleta no tiene «Atletas» y un entrenador no tiene «Mis
 * sesiones».
 */
describe("el marco", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => Promise.resolve(new Response("[]"))));
  });

  it("lleva la marca y el nombre", async () => {
    montar(<Marco>contenido</Marco>);
    const marca = screen.getByRole("link", { name: /Trainets/ });
    expect(marca).toBeVisible();
    // El símbolo es decorativo y va oculto al lector: el nombre ya está al lado,
    // y anunciarlo dos veces es ruido para quien no lo ve.
    expect(marca.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("como entrenador la navegación dice Atletas", () => {
    montar(<Marco>contenido</Marco>);
    expect(screen.getByRole("link", { name: "Atletas" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Mis sesiones" })).toBeNull();
  });

  it("el interruptor de rol no se muestra por defecto", () => {
    // Se resuelve solo: aceptar una invitación deja el rol en atleta y un 403
    // sobre el espacio del entrenador lleva a atleta a quien tenga fichas.
    montar(<Marco>contenido</Marco>);
    expect(screen.queryByText(/Estoy mirando como/)).toBeNull();
  });
});
