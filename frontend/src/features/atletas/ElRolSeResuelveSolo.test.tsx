import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { Inicio } from "../Inicio";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

/**
 * Quién termina viendo qué cuando pedir como entrenador contesta 403.
 *
 * El rol arranca en `coach`, así que un atleta que abre la aplicación desde otro
 * teléfono —o con el almacenamiento borrado— pide como entrenador y recibe ese
 * 403. Antes eso lo mandaba a «date de alta como entrenador», que es crear un
 * espacio que no vino a crear. Y el desplegable de rol, que era la salida, ahora
 * no se muestra.
 *
 * Los dos casos comparten el código de estado y se distinguen por el dato: si
 * tiene fichas como atleta, es un atleta.
 */
function responder({ fichas }: { fichas: unknown[] }) {
  const pedido = vi.fn<typeof fetch>((url, opciones) => {
    const rol = new Headers(opciones?.headers).get("Active-Role");
    if (String(url).includes("/api/athletes") && rol === "coach") {
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "todavía no sos entrenador" }), { status: 403 }),
      );
    }
    return Promise.resolve(new Response(JSON.stringify(fichas), { status: 200 }));
  });
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

/**
 * Un almacenamiento nuevo por caso, y esto no es prolijidad.
 *
 * El rol elegido se guarda en `localStorage`. En esta máquina ese objeto no
 * existe, `_guardado()` cae al `catch` y devuelve `coach` siempre — así que la
 * falta de limpieza entre casos quedaba tapada. En CI sí existe: el primer caso
 * dejaba `athlete` guardado y el segundo arrancaba ya como atleta, sin dibujar
 * nunca el alta de entrenador.
 *
 * Verde acá y rojo allá durante dos pushes, y la primera explicación que le
 * encontré —que faltaba tiempo de espera— era falsa: con cinco segundos falla
 * igual, porque el elemento no aparece nunca.
 */
function almacenamientoFalso(): Storage {
  const datos = new Map<string, string>();
  return {
    get length() {
      return datos.size;
    },
    clear: () => datos.clear(),
    getItem: (k) => datos.get(k) ?? null,
    key: (i) => [...datos.keys()][i] ?? null,
    removeItem: (k) => void datos.delete(k),
    setItem: (k, v) => void datos.set(k, v),
  };
}

describe("el rol se resuelve sin preguntarle a la persona", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", almacenamientoFalso());
  });

  it("con fichas de atleta, la pantalla pasa a ser la del atleta", async () => {
    // Se monta `Inicio` y no el listado, a propósito: el rol decide **qué
    // pantalla se dibuja**, y eso sólo cambia si el rol cambió de verdad.
    //
    // La primera versión de este test miraba que algún pedido llevara
    // `Active-Role: athlete`, y no servía: la consulta que averigua si hay
    // fichas ya fuerza ese rol, así que la cabecera aparecía igual con el
    // cambio de rol borrado. Verificado mutando: pasaba en verde.
    responder({ fichas: [{ id: "a1", full_name: "Ficha" }] });
    montar(<Inicio />);

    expect(await screen.findByText("Mis sesiones")).toBeVisible();
  });

  it("sin fichas, sigue ofreciendo darse de alta como entrenador", async () => {
    // El otro lado de la misma moneda: quien recién llega no tiene fichas, y
    // para esa persona el 403 sí tiene como salida el alta.
    responder({ fichas: [] });
    montar(<Inicio />);

    // El título exacto del alta, y no un `/entrenador/i` suelto: el estado vacío
    // del atleta dice «Tu entrenador todavía no cargó sesiones», así que la
    // expresión laxa matcheaba de los dos lados y el test pasaba con el cambio
    // de rol hecho siempre. Verificado mutando.
    expect(await screen.findByText("Todavía no tenés un espacio de entrenador")).toBeVisible();
  });

  it("no ofrece el alta mientras todavía no sabe", async () => {
    // Un parpadeo de «date de alta como entrenador» delante de un atleta es
    // ofrecerle justo lo que no vino a hacer.
    responder({ fichas: [{ id: "a1", full_name: "Ficha" }] });
    const { container } = montar(<Inicio />);
    expect(container.textContent ?? "").not.toMatch(/Todavía no tenés un espacio/);
  });
});
