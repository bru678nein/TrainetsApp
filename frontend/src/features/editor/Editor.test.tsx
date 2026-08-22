import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { montar } from "../../lib/pruebas";
import { PanelDelAtleta } from "../atletas/PanelDelAtleta";

vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const PROGRAMA = { id: "p1", name: "Programa", starts_on: null };
const MESO = {
  id: "m1",
  ordinal: 1,
  label: "Acumulación",
  week_count: 4,
  focus: null,
  rir_progression: [0, 0, -1, -1],
};
/**
 * La proyección tal como la devuelve el servidor para ese mesociclo.
 *
 * Las semanas 1 y 2 están armadas y las otras dos son predicción, que es la
 * distinción entera del panel. La carga se queda en 80 en las cuatro y el RIR
 * baja en la 3: es lo que la progresión `[0, 0, -1, -1]` produce.
 */
const serie = (rir: number) => ({
  set_number: 1,
  reps_min: 8,
  reps_max: 8,
  rir_min: rir,
  rir_max: rir,
  target_load_kg: 80,
  target_pct_1rm: null,
  is_amrap: false,
});
const dia = (rir: number) => [
  {
    day_number: 1,
    label: null,
    ejercicios: [
      { exercise_name: "Sentadilla", position: 1, superset_key: null, sets: [serie(rir)] },
    ],
  },
];
const PROYECCION = {
  semana_base: 1,
  declara_progresion: true,
  semanas: [
    { week_number: 1, rir_delta: 0, movimiento: "base", ya_armada: true, dias: dia(2) },
    { week_number: 2, rir_delta: 0, movimiento: "sostiene", ya_armada: true, dias: dia(2) },
    { week_number: 3, rir_delta: -1, movimiento: "aprieta", ya_armada: false, dias: dia(1) },
    { week_number: 4, rir_delta: -1, movimiento: "sostiene", ya_armada: false, dias: dia(1) },
  ],
};

/** Sólo las semanas 1 y 2 están armadas: la 3 y la 4 quedan vacías a propósito. */
const AGENDA = [
  { id: "s1", mesocycle_id: "m1", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 1 },
  { id: "s2", mesocycle_id: "m1", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 2 },
  { id: "s3", mesocycle_id: "m1", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 2, day_number: 1 },
];

/**
 * El orden de estas condiciones importa y por eso están de la más específica a
 * la más general: `/api/programs/p1/mesocycles` contiene `/programs`, así que
 * preguntar por el prefijo corto primero devuelve la lista equivocada y el
 * editor se queda sin bloques sin decir por qué.
 */
function cuerpoPara(url: string): unknown {
  if (url.includes("/projection")) return PROYECCION;
  if (url.includes("/mesocycles")) return [MESO];
  if (url.includes("/programs")) return [PROGRAMA];
  if (url.match(/\/api\/sessions\//)) {
    return { id: "s1", mesocycle: "Acumulación", week_number: 1, day_number: 1, blocks: [] };
  }
  if (url.includes("/sessions")) return AGENDA;
  return [];
}

function responder() {
  const pedido = vi.fn<typeof fetch>((url) =>
    Promise.resolve(new Response(JSON.stringify(cuerpoPara(String(url))), { status: 200 })),
  );
  vi.stubGlobal("fetch", pedido);
  return pedido;
}

/**
 * El editor dejó de tener dirección propia: vive como pestañas del panel del
 * atleta, al lado de las gráficas. Los casos que siguen entran por ahí.
 */
function montarEditor() {
  return montar(
    <Routes>
      <Route path="/atletas/:atletaId" element={<PanelDelAtleta />} />
    </Routes>,
    "/atletas/a1",
  );
}

describe("el riel de semanas", () => {
  beforeEach(() => vi.unstubAllGlobals());

  const riel = () => screen.getByRole("list", { name: /Semanas de/ });

  it("muestra todas las del mesociclo, armadas y vacías por igual", async () => {
    // Es lo que hace visible que la 3 no está armada. En una lista de lo que
    // hay, lo que falta no ocupa lugar y no se ve — y lo que falta es justo lo
    // que el entrenador viene a hacer.
    responder();
    montarEditor();
    await screen.findByRole("button", { name: /Semana 1/ });

    for (const n of [1, 2, 3, 4]) {
      expect(within(riel()).getByRole("button", { name: new RegExp(`Semana ${n}`) })).toBeVisible();
    }
  });

  it("dice el paso de la progresión sin abrir nada", async () => {
    // `[0, 0, -1, -1]` no se lee. El riel lo traduce contra la semana anterior,
    // que es como se piensa: se sostiene, se aprieta, se sostiene.
    responder();
    montarEditor();
    await screen.findByRole("button", { name: /Semana 1/ });

    expect(within(riel()).getByRole("button", { name: /Semana 1.*base/ })).toBeVisible();
    expect(within(riel()).getByRole("button", { name: /Semana 3.*−1 RIR/ })).toBeVisible();
    expect(within(riel()).getByRole("button", { name: /Semana 4.*igual/ })).toBeVisible();
  });

  it("marca cuáles ya tienen días", async () => {
    responder();
    montarEditor();
    await screen.findByRole("button", { name: /Semana 1/ });

    expect(within(riel()).getByRole("button", { name: /Semana 1.*armada/ })).toBeVisible();
    expect(within(riel()).queryByRole("button", { name: /Semana 3.*armada/ })).toBeNull();
  });

  it("abre una sola, y el riel dice cuál", async () => {
    // Con las cuatro abiertas había que scrollear para comparar el día 1 de dos
    // semanas, que es la comparación que el entrenador hace todo el tiempo.
    responder();
    montarEditor();
    const semana3 = await screen.findByRole("button", { name: /Semana 3/ });

    expect(screen.getByRole("heading", { name: "Semana 1" })).toBeVisible();
    await userEvent.click(semana3);
    expect(screen.getByRole("heading", { name: "Semana 3" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Semana 1" })).toBeNull();
    expect(semana3).toHaveAttribute("aria-current", "true");
  });

  it("una semana sin días lo dice, en vez de quedar en blanco", async () => {
    responder();
    montarEditor();
    await userEvent.click(await screen.findByRole("button", { name: /Semana 3/ }));
    expect(screen.getByText("Sin sesiones")).toBeVisible();
  });

  it("los días de la semana abierta se despliegan sin abrir un acordeón más", async () => {
    responder();
    montarEditor();
    const semana1 = (await screen.findByRole("heading", { name: "Semana 1" })).closest("section")!;
    expect(semana1.querySelectorAll("button[aria-expanded]")).toHaveLength(2);
  });
});

describe("abrir una sesión", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("arranca cerrada y se abre al apretarla", async () => {
    // `aria-expanded` no es sólo para el lector: la flecha gira desde ese
    // atributo, así que el estado que se anuncia y el que se dibuja son el
    // mismo. Dos fuentes se desincronizan.
    responder();
    montarEditor();
    const boton = (await screen.findAllByRole("button", { name: /Día 1/ }))[0]!;
    expect(boton).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(boton);
    expect(boton).toHaveAttribute("aria-expanded", "true");
  });

  it("abrir una cierra la anterior", async () => {
    // El contenido de una sesión es largo. Con dos abiertas hay que hacer scroll
    // para comparar lo que la rejilla acababa de poner al lado.
    responder();
    montarEditor();
    const botones = await screen.findAllByRole("button", { name: /Día/ });
    await userEvent.click(botones[0]!);
    await userEvent.click(botones[1]!);

    expect(botones[0]).toHaveAttribute("aria-expanded", "false");
    expect(botones[1]).toHaveAttribute("aria-expanded", "true");
  });
});

describe("agregar y borrar días", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("el + propone el primer día libre de la semana abierta", async () => {
    // La semana 1 tiene los días 1 y 2, así que le toca el 3; la 2 tiene el 1,
    // así que le toca el 2. El número sale de la semana abierta y no de un
    // formulario suelto que hay que completar cada vez.
    //
    // Se comprueban las dos y no una: con una sola, un `+` clavado en «día 3»
    // pasaría el test y estaría mal en todas las demás semanas.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    expect(screen.getByTitle("Agregar el día 3")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Semana 2/ }));
    expect(screen.getByTitle("Agregar el día 2")).toBeInTheDocument();
  });

  it("apretarlo crea la sesión en esa semana y ese día", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    await userEvent.click(screen.getByTitle("Agregar el día 3"));

    const alta = pedido.mock.calls.find(
      ([, o]) => o?.method === "POST" && String(o?.body).includes("week_number"),
    );
    expect(alta).toBeDefined();
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ week_number: 1, day_number: 3 });
  });

  it("una semana llena lo dice, en vez de ofrecer un botón que falla", async () => {
    // Siete días es el tope de la semana. Un `+` que contesta 409 promete algo
    // que no puede cumplir.
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const u = String(url);
        if (u.includes("/mesocycles")) return Promise.resolve(new Response(JSON.stringify([MESO])));
        if (u.includes("/programs")) return Promise.resolve(new Response(JSON.stringify([PROGRAMA])));
        if (u.match(/\/api\/sessions\//)) return Promise.resolve(new Response(JSON.stringify({})));
        if (u.includes("/sessions")) {
          const llena = [1, 2, 3, 4, 5, 6, 7].map((d) => ({
            id: `s${d}`,
            mesocycle_id: "m1",
            mesocycle: "Acumulación",
            mesocycle_ordinal: 1,
            week_number: 1,
            day_number: d,
          }));
          return Promise.resolve(new Response(JSON.stringify(llena)));
        }
        return Promise.resolve(new Response("[]"));
      }),
    );
    montarEditor();
    expect(await screen.findByText("Semana completa")).toBeInTheDocument();
    expect(screen.getByTitle("Esta semana ya tiene los siete días")).toBeDisabled();
  });

  it("cada día tiene su propio botón de borrar, nombrado", async () => {
    // El nombre accesible dice cuál se borra. «🗑» a secas se anuncia igual en
    // los tres días de la semana, y borrar no tiene deshacer.
    responder();
    montarEditor();
    expect(
      await screen.findByRole("button", { name: "Borrar el día 1 de la semana 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Borrar el día 2 de la semana 1" }),
    ).toBeInTheDocument();
  });

  it("borrar el día abierto lo cierra antes de sacarlo", async () => {
    // Si no, queda montado el contenido de una sesión que ya no existe y su
    // consulta contesta 404 sobre una pantalla que la persona no está mirando.
    responder();
    montarEditor();
    const dia = (await screen.findAllByRole("button", { name: /Día 1/ }))[0]!;
    await userEvent.click(dia);
    expect(dia).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(screen.getByRole("button", { name: "Borrar el día 1 de la semana 1" }));
    expect(dia).toHaveAttribute("aria-expanded", "false");
  });
});

describe("las dos pestañas del editor", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("arranca en mesociclos", async () => {
    responder();
    montarEditor();
    expect(await screen.findByRole("heading", { name: "Semana 1" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Agregar un ejercicio" })).not.toBeInTheDocument();
  });

  it("el catálogo vive en su propia pestaña", async () => {
    // Armar el bloque de este atleta y mantener el catálogo son cosas distintas:
    // el catálogo es del entrenador y lo comparten todos sus atletas. Juntas,
    // parecía que crear un ejercicio era parte de armar este programa.
    responder();
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));

    expect(screen.getByRole("heading", { name: "Agregar un ejercicio" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Semana 1" })).not.toBeInTheDocument();
  });

  it("el patrón de movimiento se elige del catálogo que manda el API", async () => {
    // Ni una lista escrita a mano ni un texto libre: son once filas cerradas, y
    // que sean cerradas es lo que hace contestable la pregunta por volumen.
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const u = String(url);
        if (u.includes("movement-patterns")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                { code: "rodilla_dominante", label_es: "Rodilla dominante" },
                { code: "pliometria", label_es: "PLIOMETRIA" },
              ]),
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify(cuerpoPara(u))));
      }),
    );
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));

    const patron = await screen.findByLabelText("Patrón de movimiento");
    expect([...patron.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
      "— patrón de movimiento —",
      "Rodilla dominante",
      "PLIOMETRIA",
    ]);
  });
});

describe("el catálogo", () => {
  const CATALOGO = {
    ejercicios: [
      { id: "e1", name: "Sentadilla", pattern_code: "rodilla_dominante", coach_id: "c1", prescription_count: 12 },
      { id: "e2", name: "Peso muerto", pattern_code: "bisagra", coach_id: "c1", prescription_count: 0 },
      { id: "e3", name: "Press militar", pattern_code: "empuje_vertical", coach_id: null, prescription_count: 3 },
    ],
    patrones: [
      { code: "rodilla_dominante", label_es: "Rodilla dominante", coach_id: null },
      { code: "bisagra", label_es: "Bisagra de cadera / isquios", coach_id: null },
      { code: "antebrazo", label_es: "Antebrazo", coach_id: "c1" },
    ],
  };

  function conCatalogo() {
    const pedido = vi.fn<typeof fetch>((url) => {
      const u = String(url);
      if (u.includes("movement-patterns")) {
        return Promise.resolve(new Response(JSON.stringify(CATALOGO.patrones)));
      }
      if (u.includes("/exercises")) {
        return Promise.resolve(new Response(JSON.stringify(CATALOGO.ejercicios)));
      }
      return Promise.resolve(new Response(JSON.stringify(cuerpoPara(u))));
    });
    vi.stubGlobal("fetch", pedido);
    return pedido;
  }

  async function abrirCatalogo() {
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));
  }

  beforeEach(() => vi.unstubAllGlobals());

  /** Acotado a la lista: los desplegables de los formularios repiten los textos. */
  const enElCatalogo = () => within(screen.getByRole("list", { name: "Catálogo" }));

  it("muestra los ejercicios y los patrones juntos", async () => {
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    // «Rodilla dominante» aparece dos veces adentro del catálogo y está bien:
    // como etiqueta de la sentadilla y como fila propia. Lo que se afirma es que
    // están las dos cosas, no cuántas veces se lee el texto.
    const filas = enElCatalogo()
      .getAllByRole("listitem")
      .map((f) => f.textContent ?? "");
    expect(filas.some((f) => f.includes("Sentadilla"))).toBe(true);
    expect(filas.some((f) => f.includes("Rodilla dominante") && f.includes("patrón"))).toBe(true);
  });

  it("los patrones llevan su etiqueta", async () => {
    // En una lista mezclada, «Bíceps» suelto se lee como un ejercicio.
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");
    expect(screen.getAllByText("patrón")).toHaveLength(3);
  });

  it("el filtro deja ver sólo una de las dos cosas", async () => {
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    await userEvent.click(screen.getByRole("button", { name: "Patrones" }));
    expect(enElCatalogo().queryByText("Sentadilla")).not.toBeInTheDocument();
    expect(enElCatalogo().getAllByText("Antebrazo").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "Ejercicios" }));
    expect(enElCatalogo().getByText("Sentadilla")).toBeInTheDocument();
    expect(enElCatalogo().queryByText("patrón")).not.toBeInTheDocument();
  });

  it("el buscador ignora acentos y mayúsculas", async () => {
    // Buscar "presion" tiene que encontrar "Presión": si hay que escribir el
    // acento, el buscador sirve sólo cuando ya sabés qué escribir.
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    await userEvent.type(screen.getByLabelText("Buscar en el catálogo"), "PESO");
    expect(screen.getByText("Peso muerto")).toBeInTheDocument();
    expect(screen.queryByText("Sentadilla")).not.toBeInTheDocument();
  });

  it("una búsqueda sin resultados lo dice con lo que se buscó", async () => {
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");
    await userEvent.type(screen.getByLabelText("Buscar en el catálogo"), "zancada");
    expect(screen.getByText(/No hay nada que coincida con «zancada»/)).toBeInTheDocument();
  });

  it("los propios se pueden editar y borrar; el global no", async () => {
    // El catálogo compartido se modifica con una migración, no desde la
    // aplicación. Ofrecer los botones sería prometer algo que el servidor
    // rechaza con 403.
    conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    expect(screen.getByRole("button", { name: "Editar Sentadilla" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Borrar Sentadilla" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar Press militar" })).not.toBeInTheDocument();
    expect(screen.getByText("global")).toBeInTheDocument();
  });

  it("editar manda PATCH con lo que quedó", async () => {
    const pedido = conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    await userEvent.click(screen.getByRole("button", { name: "Editar Sentadilla" }));
    const campo = screen.getByLabelText("Nombre de Sentadilla");
    await userEvent.clear(campo);
    await userEvent.type(campo, "Sentadilla frontal");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    const patch = pedido.mock.calls.find(([, o]) => o?.method === "PATCH");
    expect(patch).toBeDefined();
    expect(JSON.parse(String(patch![1]!.body)).name).toBe("Sentadilla frontal");
  });

  it("agregar un patrón manda sólo el nombre", async () => {
    // El código lo deriva el servidor. Pedir los dos es pedir dos veces lo mismo
    // y dejar que se contradigan.
    const pedido = conCatalogo();
    await abrirCatalogo();
    await screen.findByText("Sentadilla");

    await userEvent.type(screen.getByLabelText("Nombre del patrón"), "Antebrazo");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Agregar" }).at(-1)!,
    );

    const alta = pedido.mock.calls.find(
      ([u, o]) => o?.method === "POST" && String(u).includes("movement-patterns"),
    );
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ label_es: "Antebrazo" });
  });
});

describe("borrar del catálogo pide confirmación", () => {
  const CAT = {
    ejercicios: [
      { id: "e1", name: "Sentadilla", pattern_code: "rd", coach_id: "c1", prescription_count: 12 },
      { id: "e2", name: "Remo", pattern_code: "rd", coach_id: "c1", prescription_count: 0 },
    ],
    patrones: [
      { code: "rd", label_es: "Rodilla dominante", coach_id: null },
      { code: "antebrazo", label_es: "Antebrazo", coach_id: "c1" },
    ],
  };

  function conCat() {
    const pedido = vi.fn<typeof fetch>((url) => {
      const u = String(url);
      if (u.includes("movement-patterns")) {
        return Promise.resolve(new Response(JSON.stringify(CAT.patrones)));
      }
      if (u.includes("/exercises")) {
        return Promise.resolve(new Response(JSON.stringify(CAT.ejercicios)));
      }
      return Promise.resolve(new Response(JSON.stringify(cuerpoPara(u))));
    });
    vi.stubGlobal("fetch", pedido);
    return pedido;
  }

  async function abrir() {
    montarEditor();
    await userEvent.click(await screen.findByRole("tab", { name: "Ejercicios" }));
    await screen.findByText("Sentadilla");
  }

  beforeEach(() => vi.unstubAllGlobals());

  it("apretar el tacho no borra: abre el diálogo", async () => {
    const pedido = conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Sentadilla" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(pedido.mock.calls.some(([, o]) => o?.method === "DELETE")).toBe(false);
  });

  it("dice en cuántos días está y qué sobrevive", async () => {
    // Una confirmación que no dice qué se lleva puesto no es una decisión, es un
    // trámite. Y lo que tranquiliza es cierto: el registro del atleta sobrevive
    // con su copia congelada de lo que se le pidió.
    conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Sentadilla" }));

    const dialogo = within(screen.getByRole("dialog"));
    expect(dialogo.getByText(/12/)).toBeInTheDocument();
    expect(dialogo.getByText(/no se pierde/i)).toBeInTheDocument();
    expect(dialogo.getByText(/no se puede deshacer/i)).toBeInTheDocument();
  });

  it("uno sin usar lo dice, en vez de inventar un número", async () => {
    conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Remo" }));
    expect(within(screen.getByRole("dialog")).getByText(/ningún día/i)).toBeInTheDocument();
  });

  it("cancelar no borra", async () => {
    const pedido = conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Sentadilla" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(pedido.mock.calls.some(([, o]) => o?.method === "DELETE")).toBe(false);
  });

  it("confirmar manda el DELETE con la confirmación", async () => {
    // La API se niega por defecto a sacarlo de los días: un cliente que no
    // pregunte no arrasa un programa por descuido.
    const pedido = conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Sentadilla" }));
    await userEvent.click(screen.getByRole("button", { name: "Borrar" }));

    const baja = pedido.mock.calls.find(([, o]) => o?.method === "DELETE");
    expect(String(baja![0])).toContain("/api/exercises/e1?confirmar=true");
  });

  it("el que arranca enfocado es cancelar y no borrar", async () => {
    // Confirmar tiene que costar un movimiento: con el foco en el botón que
    // destruye, un Enter de más borra un ejercicio.
    //
    // Se afirma sobre el atributo y no sobre `document.activeElement` porque
    // dónde queda el foco al abrir lo decide `showModal`, y en jsdom eso es un
    // sustituto nuestro. Afirmarlo ahí sería verificar el sustituto.
    conCat();
    await abrir();
    await userEvent.click(screen.getByRole("button", { name: "Borrar Sentadilla" }));

    // React no renderiza el atributo: enfoca al montar. Por eso el contenido del
    // diálogo se monta recién al abrirse — con los botones montados de entrada,
    // el foco se lo llevaba la pantalla al cargar.
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancelar" }));
  });

  it("el patrón propio se puede borrar; el de la base común no", async () => {
    conCat();
    await abrir();
    expect(screen.getByRole("button", { name: "Borrar el patrón Antebrazo" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Borrar el patrón Rodilla dominante" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("base común")).toBeInTheDocument();
  });
});

describe("elegir el ejercicio de una sesión", () => {
  const EJERCICIOS = [
    { id: "e1", name: "Sentadilla", pattern_code: "rd", coach_id: "c1", prescription_count: 0 },
    { id: "e2", name: "Prensa", pattern_code: "rd", coach_id: "c1", prescription_count: 0 },
    { id: "e3", name: "Peso muerto", pattern_code: "bisagra", coach_id: "c1", prescription_count: 0 },
  ];
  const PATRONES = [
    { code: "rd", label_es: "Rodilla dominante", coach_id: null },
    { code: "bisagra", label_es: "Bisagra de cadera / isquios", coach_id: null },
  ];

  function conCatalogo() {
    const pedido = vi.fn<typeof fetch>((url) => {
      const u = String(url);
      if (u.includes("movement-patterns")) {
        return Promise.resolve(new Response(JSON.stringify(PATRONES)));
      }
      if (u.includes("/exercises")) return Promise.resolve(new Response(JSON.stringify(EJERCICIOS)));
      return Promise.resolve(new Response(JSON.stringify(cuerpoPara(u))));
    });
    vi.stubGlobal("fetch", pedido);
    return pedido;
  }

  async function abrirUnDia() {
    montarEditor();
    await userEvent.click((await screen.findAllByRole("button", { name: /Día 1/ }))[0]!);
    await screen.findByLabelText("Ejercicio");
  }

  const opcionesDe = (etiqueta: string) =>
    [...screen.getByLabelText<HTMLSelectElement>(etiqueta).querySelectorAll("option")].map(
      (o) => o.textContent,
    );

  beforeEach(() => vi.unstubAllGlobals());

  it("sin filtro están todos los ejercicios", async () => {
    conCatalogo();
    await abrirUnDia();
    expect(opcionesDe("Ejercicio")).toEqual([
      "— elegí un ejercicio —",
      "Sentadilla",
      "Prensa",
      "Peso muerto",
    ]);
  });

  it("el patrón acota la lista, no agrega un dato", async () => {
    // La prescripción sólo apunta al ejercicio, y el ejercicio ya trae su
    // patrón. Guardarlo dos veces sería dejar que se contradigan: una sentadilla
    // cargada como empuje vertical rompe el volumen sin que nada avise.
    conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Filtrar por patrón de movimiento"), "rd");

    expect(opcionesDe("Ejercicio")).toEqual(["— elegí un ejercicio —", "Sentadilla", "Prensa"]);
  });

  it("cambiar de patrón limpia lo elegido", async () => {
    // Un `select` cuyo valor no figura entre sus opciones se dibuja vacío y
    // manda el viejo al enviar: se agregaría un ejercicio que la pantalla ya no
    // muestra.
    conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e3");
    await userEvent.selectOptions(screen.getByLabelText("Filtrar por patrón de movimiento"), "rd");

    expect(screen.getByLabelText<HTMLSelectElement>("Ejercicio").value).toBe("");
  });

  const altaDe = (pedido: ReturnType<typeof conCatalogo>) =>
    JSON.parse(
      String(
        pedido.mock.calls.find(
          ([u, o]) => o?.method === "POST" && String(u).includes("/prescriptions"),
        )![1]!.body,
      ),
    );

  it("el ejercicio nace con sus series, en un solo pedido", async () => {
    // 473 de 473 ejercicios prescriptos de la programación real tienen todas
    // sus series idénticas. Pedirlas de a una eran 84 de las 105 interacciones
    // de un día.
    const pedido = conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    const cuerpo = altaDe(pedido);
    expect(cuerpo.exercise_id).toBe("e1");
    expect(cuerpo.sets).toHaveLength(3);
    expect(cuerpo.sets[0]).toEqual({
      reps_min: 8,
      reps_max: 8,
      rir_min: 2,
      rir_max: 2,
      target_load_kg: null,
    });

    // Un solo POST. Con uno por serie, un fallo a la mitad deja el ejercicio
    // creado y vacío, que es lo que el atleta ve como un día roto.
    const posts = pedido.mock.calls.filter(
      ([u, o]) => o?.method === "POST" && String(u).includes("/prescription"),
    );
    expect(posts).toHaveLength(1);
  });

  it("la cantidad de series elegida es la que se manda", async () => {
    const pedido = conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.selectOptions(screen.getByLabelText("Series"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(altaDe(pedido).sets).toHaveLength(5);
  });

  it("sin kg la serie va autorregulada, no en cero", async () => {
    // Cero no es "sin peso": cero es una barra vacía y cuenta como carga en el
    // tonelaje. La diferencia se ve en el análisis, no en la pantalla.
    const pedido = conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(altaDe(pedido).sets[0].target_load_kg).toBeNull();
  });

  it("con kg la serie lleva la carga", async () => {
    const pedido = conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.type(screen.getByLabelText("Kg"), "80");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(altaDe(pedido).sets[0].target_load_kg).toBe(80);
  });

  it("agregar un ejercicio avisa, y dice cuántas series creó", async () => {
    // El aviso no es decoración: el editor vuelve a pedir el árbol entero
    // después de guardar, y cuando el cambio cae fuera de la pantalla no queda
    // ninguna señal de que algo pasó. La duda lleva a apretar de nuevo.
    conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(await screen.findByText("Ejercicio agregado con 3 series")).toBeInTheDocument();
  });

  it("el aviso sigue a lo elegido, no al texto del botón", async () => {
    conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");
    await userEvent.selectOptions(screen.getByLabelText("Series"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(await screen.findByText("Ejercicio agregado con 5 series")).toBeInTheDocument();
  });

  it("un guardado que falla no dice que salió bien", async () => {
    // El aviso cuelga de `onSuccess`. Colgarlo del click confirmaría escrituras
    // que el servidor rechazó, que es peor que no avisar nada.
    conCatalogo();
    await abrirUnDia();
    await userEvent.selectOptions(screen.getByLabelText("Ejercicio"), "e1");

    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url, opciones) =>
        (opciones as RequestInit | undefined)?.method === "POST"
          ? Promise.resolve(new Response(JSON.stringify({ detail: "no" }), { status: 409 }))
          : Promise.resolve(new Response(JSON.stringify(cuerpoPara(String(url))), { status: 200 })),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Agregar ejercicio" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/Ejercicio agregado/)).not.toBeInTheDocument();
  });
});

describe("duplicar una semana", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("dice adónde va y cuánto mueve el RIR antes de apretar", async () => {
    // Es la razón por la que duplicar sirve. Decirlo después sería una sorpresa
    // sobre una semana que el atleta puede empezar a entrenar mañana.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    expect(screen.getByLabelText("Semana de destino")).toBeVisible();
    expect(screen.getByText(/aplica -1 RIR/)).toBeVisible();
  });

  it("sólo ofrece como destino las semanas vacías", async () => {
    // Pisar una semana armada el servidor lo rechaza con 409 —el atleta pudo
    // haber registrado series ahí— así que no se ofrece un destino que va a
    // contestar un error.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    const opciones = within(screen.getByLabelText("Semana de destino"))
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(opciones).toEqual(["Semana 3", "Semana 4"]);
  });

  it("no aparece sobre una semana que no tiene nada que copiar", async () => {
    responder();
    montarEditor();
    await userEvent.click(await screen.findByRole("button", { name: /Semana 3/ }));
    expect(screen.queryByLabelText("Semana de destino")).toBeNull();
  });

  it("manda el origen y el destino elegidos", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    await userEvent.selectOptions(screen.getByLabelText("Semana de destino"), "4");
    await userEvent.click(screen.getByRole("button", { name: "Duplicar la semana" }));

    const llamada = pedido.mock.calls.find(([u, o]) =>
      String(u).includes("duplicate-week") && o?.method === "POST",
    );
    expect(llamada).toBeDefined();
    expect(JSON.parse(String(llamada![1]!.body))).toEqual({ from_week: 1, to_week: 4 });
  });
});

describe("duplicar y pegar bloques", () => {
  beforeEach(() => vi.unstubAllGlobals());

  /**
   * Tres bloques: dos armados y uno vacío.
   *
   * El tercero armado **y sin copiar** es el que hace falta: con sólo dos, el
   * armado es siempre el copiado, así que `!esteCopiado` ya lo excluye y la
   * condición de «sólo en los vacíos» no decide nada. Con dos bloques la
   * mutación que la borraba pasaba en verde.
   */
  function conTresBloques() {
    const SEGUNDO = { ...MESO, id: "m2", ordinal: 2, label: "Intensificación" };
    const VACIO = { ...MESO, id: "m3", ordinal: 3, label: "Descarga" };
    const AGENDA_3 = [
      ...AGENDA,
      { id: "s9", mesocycle_id: "m2", mesocycle: "Intensificación", mesocycle_ordinal: 2, week_number: 1, day_number: 1 },
    ];
    const pedido = vi.fn<typeof fetch>((url) => {
      const u = String(url);
      const cuerpo = u.includes("/mesocycles/")
        ? { id: "m4" }
        : u.includes("/mesocycles")
          ? [MESO, SEGUNDO, VACIO]
          : u.match(/\/api\/sessions\//)
            ? { id: "s1", mesocycle: "Acumulación", week_number: 1, day_number: 1, blocks: [] }
            : u.includes("/sessions")
              ? AGENDA_3
              : cuerpoPara(u);
      return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
    });
    vi.stubGlobal("fetch", pedido);
    return pedido;
  }

  it("con un solo bloque ofrece duplicar y no copiar", async () => {
    // Con uno solo no hay dónde pegar, así que «Copiar» sería un botón que no
    // lleva a ningún lado. Para crear el segundo está «Duplicar», de un toque.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });

    expect(screen.getByRole("button", { name: "Duplicar el bloque" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Copiar el bloque/ })).toBeNull();
  });

  it("duplicar crea uno nuevo, sin destino", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });
    await userEvent.click(screen.getByRole("button", { name: "Duplicar el bloque" }));

    const alta = pedido.mock.calls.find(([u]) => String(u).includes("/duplicate"));
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ to_mesocycle: null });
  });

  it("copiar aparece en el bloque abierto cuando hay más de uno", async () => {
    // Con uno solo no hay dónde pegar. Con varios, se copia el que está abierto
    // y el destino se elige moviéndose por la tira, que no se va de la pantalla.
    conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });

    expect(screen.getByRole("button", { name: /Copiar el bloque/ })).toBeVisible();
  });

  it("pegar aparece recién en un bloque vacío, y no en el copiado", async () => {
    conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });

    // Sin copiar nada no hay dónde pegar.
    expect(screen.queryByRole("button", { name: /Pegar el bloque/ })).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /Copiar el bloque/ }));
    // Sobre sí mismo tampoco: el servidor lo rechaza.
    expect(screen.queryByRole("button", { name: /Pegar el bloque/ })).toBeNull();

    // El segundo está armado: pegar ahí pisaría trabajo hecho.
    await userEvent.click(screen.getByRole("button", { name: /Intensificación/ }));
    expect(screen.queryByRole("button", { name: /Pegar el bloque/ })).toBeNull();

    // El tercero está vacío. Ahí sí.
    await userEvent.click(screen.getByRole("button", { name: /Descarga/ }));
    expect(screen.getByRole("button", { name: /Pegar el bloque/ })).toBeVisible();
  });

  it("pegar manda el origen en la ruta y el destino en el cuerpo", async () => {
    const pedido = conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });

    await userEvent.click(screen.getByRole("button", { name: /Copiar el bloque/ }));
    await userEvent.click(screen.getByRole("button", { name: /Descarga/ }));
    await userEvent.click(screen.getByRole("button", { name: /Pegar el bloque/ }));

    const llamada = pedido.mock.calls.find(
      ([u, o]) => String(u).includes("/duplicate") && o?.method === "POST",
    );
    expect(String(llamada![0])).toContain("/mesocycles/m1/duplicate");
    expect(JSON.parse(String(llamada![1]!.body))).toEqual({ to_mesocycle: "m3" });
  });
});

describe("dos bloques que se llaman igual", () => {
  beforeEach(() => vi.unstubAllGlobals());

  /**
   * El caso que rompía. La agenda trae las sesiones de **todos** los programas
   * del atleta, y el editor las agrupaba por el nombre del bloque — que lo
   * escribe el entrenador y puede repetir.
   *
   * Dos «Acumulación» se mostraban las sesiones entre ellos: el vacío parecía
   * lleno, sus días salían duplicados, y pegar no aparecía nunca porque el
   * bloque nunca se veía vacío.
   */
  function conNombresRepetidos() {
    const GEMELO = { ...MESO, id: "m2", ordinal: 2, label: "Acumulación" };
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const u = String(url);
        const cuerpo = u.includes("/mesocycles/")
          ? { id: "m9" }
          : u.includes("/mesocycles")
            ? [MESO, GEMELO]
            : u.match(/\/api\/sessions\//)
              ? { id: "s1", mesocycle: "Acumulación", week_number: 1, day_number: 1, blocks: [] }
              : u.includes("/sessions")
                ? AGENDA
                : cuerpoPara(u);
        return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
      }),
    );
  }

  it("las sesiones quedan sólo en el bloque al que pertenecen", async () => {
    conNombresRepetidos();
    montarEditor();
    // Se espera a la semana y no al encabezado del bloque: el bloque se dibuja
    // antes de que la agenda resuelva, y ahí todavía no hay ningún día.
    await screen.findByRole("heading", { name: "Semana 1" });

    // El primero tiene los dos días de la semana 1. Se cuentan dentro de la
    // semana abierta y no sobre el documento: `aria-expanded` lo lleva cualquier
    // control que despliegue algo —el «+ Bloque» de la tira, por ejemplo— y
    // contarlos todos hace que este caso se rompa cada vez que aparece uno.
    const dias = () =>
      screen.getByRole("heading", { name: "Semana 1" }).closest("section")!
        .querySelectorAll("button[aria-expanded]");
    expect(dias()).toHaveLength(2);

    // El segundo se llama igual y está vacío. Ése es el cero que este caso
    // vigila: agrupar por nombre en vez de por id le llenaba las semanas con los
    // días del otro, y el bloque vacío parecía lleno.
    await userEvent.click(screen.getByRole("button", { name: /2.*Acumulación/ }));
    expect(dias()).toHaveLength(0);
    expect(screen.getByText("Sin sesiones")).toBeVisible();
  });

  it("y el bloque vacío ofrece pegar, aunque el otro se llame igual", async () => {
    conNombresRepetidos();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    await userEvent.click(screen.getByRole("button", { name: /Copiar el bloque/ }));
    await userEvent.click(screen.getByRole("button", { name: /2.*Acumulación/ }));
    expect(screen.getByRole("button", { name: /Pegar el bloque/ })).toBeVisible();
  });
});

describe("la proyección del bloque", () => {
  beforeEach(() => vi.unstubAllGlobals());

  const abrir = async () => {
    responder();
    montarEditor();
    await userEvent.click(await screen.findByRole("button", { name: "Ver la proyección" }));
  };

  it("no se pide hasta que alguien la abre", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("button", { name: "Ver la proyección" });
    expect(pedido.mock.calls.filter(([u]) => String(u).includes("/projection"))).toHaveLength(0);
  });

  it("dice el paso de cada semana en palabras y no en el número crudo", async () => {
    // `[0, 0, -1, -1]` no se lee. «−1 RIR» leído contra la semana anterior, sí.
    await abrir();
    expect(await screen.findByText("arranca acá")).toBeInTheDocument();
    expect(screen.getAllByText("igual que la anterior")).toHaveLength(2);
    expect(screen.getByText("−1 RIR: más cerca del fallo")).toBeInTheDocument();
  });

  it("separa lo que está guardado de lo que es una predicción", async () => {
    // Sin esto las cuatro semanas se leen como si ya existieran, y dos no.
    //
    // Acotado al panel: el riel también marca «armada», y contar las dos listas
    // juntas haría pasar el test aunque la proyección no marcara ninguna.
    await abrir();
    const panel = (await screen.findByText("arranca acá")).closest("ol")!;
    expect(within(panel).getAllByText("armada")).toHaveLength(2);
  });

  it("muestra que lo que se mueve es el RIR y no la carga", async () => {
    // La mitad de lo que el panel tiene para decir es que la carga se queda
    // quieta: es la decisión de diseño del producto entero.
    await abrir();
    // Acotado a la lista de la proyección: el editor también titula sus paneles
    // «Semana 3», y `findByText` a secas encuentra los dos.
    const lista = (await screen.findByText("arranca acá")).closest("ol")!;
    const semana3 = within(lista).getByText("Semana 3").closest("li")!;
    expect(within(semana3).getByText(/RIR 1/)).toBeInTheDocument();
    expect(within(semana3).getByText(/80 kg/)).toBeInTheDocument();
  });

  it("un bloque sin nada armado no proyecta nada", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>((url) => {
        const cuerpo = String(url).includes("/projection")
          ? { semana_base: null, declara_progresion: true, semanas: [] }
          : cuerpoPara(String(url));
        return Promise.resolve(new Response(JSON.stringify(cuerpo), { status: 200 }));
      }),
    );
    montarEditor();
    await userEvent.click(await screen.findByRole("button", { name: "Ver la proyección" }));
    expect(await screen.findByText(/Todavía no hay nada armado/)).toBeInTheDocument();
  });
});
