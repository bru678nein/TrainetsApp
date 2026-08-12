import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { montar } from "../../lib/pruebas";
import { Invitar } from "./Invitar";

/**
 * Se stubea `fetch` y no el módulo del API, a diferencia de las pantallas de
 * analítica.
 *
 * Dos razones. La primera es cobertura: así corre el cliente de verdad, con su
 * método, sus cabeceras y su lectura del `detail` del cuerpo, que es justamente
 * lo que estas pantallas estrenan. La segunda es que mockear el módulo con una
 * mutación adentro deja el rechazo sin manejar y vitest lo reporta como falla
 * aunque la pantalla haya hecho lo correcto.
 */
vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const CREADA = { token: "tok-abc", expires_at: "2026-08-19T12:00:00Z" };

function responder(estado: number, cuerpo: unknown) {
  const fetchFalso = vi.fn<typeof fetch>(() =>
    Promise.resolve(new Response(JSON.stringify(cuerpo), { status: estado })),
  );
  vi.stubGlobal("fetch", fetchFalso);
  return fetchFalso;
}

/** La llamada que se hizo, o un fallo que dice que no se hizo ninguna. */
function llamada(pedido: Mock<typeof fetch>) {
  const hecha = pedido.mock.calls[0];
  if (!hecha) throw new Error("No hubo ninguna llamada al API");
  return { url: String(hecha[0]), opciones: hecha[1] ?? {} };
}

describe("generar el link", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("no llama al API hasta que alguien lo pide", () => {
    // Emitir invalida la invitación anterior. Si esto saliera al montar, entrar
    // al panel de un atleta rompería el link que se le mandó ayer.
    const pedido = responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    expect(pedido).not.toHaveBeenCalled();
  });

  it("pega con POST contra la ficha que se está mirando", async () => {
    const pedido = responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    await screen.findByLabelText(/link de invitación/i);

    const { url, opciones } = llamada(pedido);
    expect(url).toContain("/api/athletes/a1/invitation");
    expect(opciones.method).toBe("POST");
  });

  it("va como entrenador, que es quien invita", async () => {
    const pedido = responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    await screen.findByLabelText(/link de invitación/i);

    const { opciones } = llamada(pedido);
    expect(new Headers(opciones.headers).get("Active-Role")).toBe("coach");
  });

  it("muestra el link completo, armado con el origen actual", async () => {
    responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    const campo = await screen.findByLabelText<HTMLInputElement>(/link de invitación/i);
    expect(campo.value).toBe(`${window.location.origin}/invitacion/tok-abc`);
  });

  it("avisa que no se vuelve a mostrar", async () => {
    // La base guarda el hash: ninguna ruta puede mostrarlo otra vez. Si la
    // pantalla no lo dice, quien cierre la pestaña pierde el link y no tiene
    // forma de saber que lo perdió.
    responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/no se vuelve a mostrar/i)).toBeInTheDocument();
  });

  it("dice cuándo vence", async () => {
    responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/19 de agosto/i)).toBeInTheDocument();
  });

  it("después de generar, el botón dice que el próximo invalida éste", async () => {
    responder(201, CREADA);
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    await screen.findByLabelText(/link de invitación/i);
    expect(screen.getByRole("button")).toHaveTextContent(/invalida el anterior/i);
  });
});

describe("cuando el API rechaza", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("un vínculo archivado dice qué hacer", async () => {
    // Es el único rechazo con salida: reactivar. Un "no se pudo" genérico deja a
    // la persona sin saber que la tiene.
    responder(409, { detail: "vinculo_archivado" });
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Reactivalo antes de invitar/i);
  });

  it("cualquier otro error no se disfraza", async () => {
    responder(500, { detail: "algo interno" });
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo generar el link/i);
  });

  it("y no muestra ningún link", async () => {
    responder(500, {});
    montar(<Invitar atletaId="a1" />);
    await userEvent.click(screen.getByRole("button"));
    await screen.findByRole("alert");
    expect(screen.queryByLabelText(/link de invitación/i)).not.toBeInTheDocument();
  });
});
