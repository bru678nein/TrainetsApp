import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { montar } from "../../lib/pruebas";
import { SesionDelDia } from "./Entrenar";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const SESION = {
  id: "s1",
  mesocycle: "Acumulación",
  week_number: 2,
  day_number: 1,
  blocks: [
    {
      prescription_id: "p1",
      exercise: "Sentadilla",
      pattern: "rodilla_dominante",
      rest_seconds: 120,
      coach_note: null,
      sets: [
        {
          id: "ps1",
          set_number: 1,
          reps_min: 8,
          reps_max: 8,
          rir_min: 2,
          rir_max: 2,
          target_load_kg: 80,
          reps_done: null,
          load_done_kg: null,
          rir_done: null,
        },
      ],
    },
  ],
};

function responder() {
  const pedido = vi.fn<typeof fetch>((url) => {
    if (String(url).includes("/log")) {
      return Promise.resolve(new Response(JSON.stringify({ id: "l1" }), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify(SESION), { status: 200 }));
  });
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

function llamadaDeRegistro(pedido: Mock<typeof fetch>) {
  const hecha = pedido.mock.calls.find(([url]) => String(url).includes("/log"));
  if (!hecha) throw new Error("No se registró ninguna serie");
  return { url: String(hecha[0]), opciones: hecha[1] ?? {} };
}

function montarSesion() {
  return montar(
    <Routes>
      <Route path="/entrenar/:sesionId" element={<SesionDelDia />} />
    </Routes>,
    "/entrenar/s1",
  );
}

describe("registrar una serie desde el gimnasio", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("los campos vienen con lo que le prescribieron", async () => {
    // Es la decisión de diseño que esta pantalla sí respeta aunque sea fea: el
    // gesto normal es confirmar, no escribir. Con una mano y treinta segundos de
    // descanso, un formulario en blanco no se usa — y sin registros, el resto del
    // producto no existe.
    responder();
    montarSesion();
    const reps = await screen.findByLabelText<HTMLInputElement>(/Repeticiones de la serie 1/);
    expect(reps.value).toBe("8");
    expect(screen.getByLabelText<HTMLInputElement>(/Carga de la serie 1/).value).toBe("80");
    expect(screen.getByLabelText<HTMLInputElement>(/RIR de la serie 1/).value).toBe("2");
  });

  it("confirmar manda lo prescrito sin tocar nada", async () => {
    const pedido = responder();
    montarSesion();
    await userEvent.click(await screen.findByRole("button", { name: "Listo" }));

    const { url, opciones } = llamadaDeRegistro(pedido);
    expect(url).toContain("/api/sets/ps1/log");
    expect(opciones.method).toBe("PUT");
    expect(JSON.parse(String(opciones.body))).toMatchObject({ reps: 8, load_kg: 80, rir: 2 });
  });

  it("va como atleta y no con el rol del interruptor", async () => {
    // Registrar es del atleta y la policy rechaza al entrenador. Si esto tomara
    // el rol del contexto, el botón contestaría 409 según cómo quedó un `select`
    // en otra pantalla.
    const pedido = responder();
    montarSesion();
    await userEvent.click(await screen.findByRole("button", { name: "Listo" }));

    const { opciones } = llamadaDeRegistro(pedido);
    expect(new Headers(opciones.headers).get("Active-Role")).toBe("athlete");
  });

  it("saltarla lo dice, en vez de mandar ceros", async () => {
    // Cero repeticiones es "fue al fallo en la primera"; saltada es "no la hizo".
    // La diferencia la usa la adherencia.
    const pedido = responder();
    montarSesion();
    await userEvent.click(await screen.findByRole("button", { name: "La salté" }));

    const { opciones } = llamadaDeRegistro(pedido);
    expect(JSON.parse(String(opciones.body))).toMatchObject({ was_skipped: true });
  });

  it("un campo vacío viaja como nulo y no como cero", async () => {
    // Sin peso es "lo elige el atleta". Cero es una barra vacía, y cuenta como
    // carga en el tonelaje.
    const pedido = responder();
    montarSesion();
    await userEvent.clear(await screen.findByLabelText(/Carga de la serie 1/));
    await userEvent.click(screen.getByRole("button", { name: "Listo" }));

    const { opciones } = llamadaDeRegistro(pedido);
    expect(JSON.parse(String(opciones.body)).load_kg).toBeNull();
  });
});
