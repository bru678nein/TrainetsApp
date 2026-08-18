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

const serie = (n: number, hecha: boolean) => ({
  id: `ps${n}`,
  set_number: n,
  reps_min: 8,
  reps_max: 8,
  rir_min: 2,
  rir_max: 2,
  target_load_kg: 80,
  // Lo hecho distinto de lo prescripto a propósito: si coincidieran, un test
  // que lee «8 reps» no distinguiría si la fila muestra lo que la persona hizo
  // o lo que le pidieron, que es exactamente la propiedad que verifica.
  reps_done: hecha ? 9 : null,
  load_done_kg: hecha ? 82.5 : null,
  rir_done: hecha ? 1 : null,
});

const DIA = {
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
      sets: [serie(1, true), serie(2, false), serie(3, false)],
    },
    {
      prescription_id: "p2",
      exercise: "Press de banca",
      pattern: "empuje_horizontal",
      rest_seconds: null,
      coach_note: null,
      sets: [serie(4, false)],
    },
  ],
};

function responderCon(cuerpo: unknown) {
  const pedido = vi.fn<typeof fetch>((url) =>
    Promise.resolve(
      new Response(JSON.stringify(String(url).includes("/log") ? { id: "l1" } : cuerpo), {
        status: 200,
      }),
    ),
  );
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

describe("una serie abierta por vez", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("sólo la próxima sin registrar tiene campos", async () => {
    // La versión anterior mostraba las 21 series de un día abiertas a la vez:
    // 5.417px y 105 controles, medido a 375px. La tarea principal era scrollear
    // hasta encontrar cuál seguía.
    responderCon(DIA);
    montarSesion();
    await screen.findByText("Sentadilla");

    // Un solo juego de campos en toda la pantalla.
    expect(screen.getAllByLabelText("Reps")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Registrar serie" })).toHaveLength(1);
    // Y es la 2: la 1 está hecha.
    expect(screen.getByText("Serie 2")).toBeVisible();
  });

  it("lo ya hecho se lee en un renglón, con lo que la persona hizo", async () => {
    responderCon(DIA);
    montarSesion();
    await screen.findByText("Sentadilla");

    expect(screen.getByText("9 reps")).toBeVisible();
    expect(screen.getByText("82.5 kg")).toBeVisible();
    expect(screen.getByText("RIR 1")).toBeVisible();
    expect(screen.getByRole("button", { name: "Corregir" })).toBeVisible();
  });

  it("corregir vuelve a abrir esa serie y no otra", async () => {
    // Sin esto, una serie mal cargada queda mal para siempre desde el teléfono.
    responderCon(DIA);
    montarSesion();
    await userEvent.click(await screen.findByRole("button", { name: "Corregir" }));

    expect(screen.getByText("Serie 1")).toBeVisible();
    expect(screen.getAllByLabelText("Reps")).toHaveLength(1);
  });

  it("el segundo ejercicio está cerrado y se abre tocándolo", async () => {
    responderCon(DIA);
    montarSesion();
    const cerrado = await screen.findByRole("button", { name: /Press de banca/ });
    expect(screen.getAllByLabelText("Reps")).toHaveLength(1);

    await userEvent.click(cerrado);
    expect(screen.getByText("Serie 4")).toBeVisible();
  });

  it("el progreso cuenta ejercicios completos, no series", async () => {
    // Un ejercicio a medias no está hecho. Contar series daría 1 de 4 y leería
    // como progreso donde no lo hay.
    responderCon(DIA);
    montarSesion();
    await screen.findByText("Sentadilla");

    expect(screen.getByText("0 de 2")).toBeVisible();
    const barra = screen.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "0");
    expect(barra).toHaveAttribute("aria-valuemax", "2");
  });

  it("el objetivo del ejercicio se lee de un vistazo", async () => {
    responderCon(DIA);
    montarSesion();
    expect(await screen.findByText("3×8 @ 80 kg")).toBeVisible();
  });
});

describe("empujar el número en vez de escribirlo", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("«+» sube y «−» baja", async () => {
    responderCon(SESION);
    montarSesion();
    const reps = await screen.findByLabelText<HTMLInputElement>("Reps");
    expect(reps.value).toBe("8");

    await userEvent.click(screen.getByLabelText("Subir Reps"));
    expect(reps.value).toBe("9");
    await userEvent.click(screen.getByLabelText("Bajar Reps"));
    await userEvent.click(screen.getByLabelText("Bajar Reps"));
    expect(reps.value).toBe("7");
  });

  it("la carga se mueve de a 2,5 kg, que es el disco más chico", async () => {
    responderCon(SESION);
    montarSesion();
    const kg = await screen.findByLabelText<HTMLInputElement>("Kg");
    await userEvent.click(screen.getByLabelText("Subir Kg"));
    expect(kg.value).toBe("82.5");
  });

  it("no baja de cero", async () => {
    // Un RIR negativo no existe y la columna tiene un CHECK que lo rechaza.
    responderCon(SESION);
    montarSesion();
    const rir = await screen.findByLabelText<HTMLInputElement>("RIR");
    const bajar = screen.getByLabelText("Bajar RIR");
    for (let i = 0; i < 4; i++) await userEvent.click(bajar);
    expect(rir.value).toBe("0");
  });

  it("el campo sigue aceptando que se escriba", async () => {
    // Un valor lejano al prescripto son muchos toques. Los botones son el camino
    // rápido, no el único.
    responderCon(SESION);
    montarSesion();
    const kg = await screen.findByLabelText<HTMLInputElement>("Kg");
    await userEvent.clear(kg);
    await userEvent.type(kg, "100");
    expect(kg.value).toBe("100");
  });
});

describe("registrar una serie desde el gimnasio", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("los campos vienen con lo que le prescribieron", async () => {
    // Es la decisión de diseño que esta pantalla sí respeta aunque sea fea: el
    // gesto normal es confirmar, no escribir. Con una mano y treinta segundos de
    // descanso, un formulario en blanco no se usa — y sin registros, el resto del
    // producto no existe.
    responder();
    montarSesion();
    const reps = await screen.findByLabelText<HTMLInputElement>("Reps");
    expect(reps.value).toBe("8");
    expect(screen.getByLabelText<HTMLInputElement>("Kg").value).toBe("80");
    expect(screen.getByLabelText<HTMLInputElement>("RIR").value).toBe("2");
  });

  it("confirmar manda lo prescrito sin tocar nada", async () => {
    const pedido = responder();
    montarSesion();
    await userEvent.click(await screen.findByRole("button", { name: "Registrar serie" }));

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
    await userEvent.click(await screen.findByRole("button", { name: "Registrar serie" }));

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
    await userEvent.clear(await screen.findByLabelText("Kg"));
    await userEvent.click(screen.getByRole("button", { name: "Registrar serie" }));

    const { opciones } = llamadaDeRegistro(pedido);
    expect(JSON.parse(String(opciones.body)).load_kg).toBeNull();
  });
});
