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
/** Sólo las semanas 1 y 2 están armadas: la 3 y la 4 quedan vacías a propósito. */
const AGENDA = [
  { id: "s1", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 1 },
  { id: "s2", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 1, day_number: 2 },
  { id: "s3", mesocycle: "Acumulación", mesocycle_ordinal: 1, week_number: 2, day_number: 1 },
];

/**
 * El orden de estas condiciones importa y por eso están de la más específica a
 * la más general: `/api/programs/p1/mesocycles` contiene `/programs`, así que
 * preguntar por el prefijo corto primero devuelve la lista equivocada y el
 * editor se queda sin bloques sin decir por qué.
 */
function cuerpoPara(url: string): unknown {
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

describe("las semanas del bloque", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("dibuja todas las del mesociclo, no sólo las que tienen sesiones", async () => {
    // Es lo que hace visible que la 3 no está armada. En una lista de lo que
    // hay, lo que falta no ocupa lugar y no se ve.
    responder();
    montarEditor();
    for (const n of [1, 2, 3, 4]) {
      expect(await screen.findByRole("heading", { name: `Semana ${n}` })).toBeInTheDocument();
    }
  });

  it("una semana sin sesiones lo dice, en vez de quedar en blanco", async () => {
    responder();
    montarEditor();
    expect(await screen.findAllByText("Sin sesiones")).toHaveLength(2);
  });

  it("cada sesión de la semana queda bajo su panel", async () => {
    responder();
    montarEditor();
    const semana1 = (await screen.findByRole("heading", { name: "Semana 1" })).closest("section")!;
    const semana2 = (await screen.findByRole("heading", { name: "Semana 2" })).closest("section")!;
    expect(semana1.querySelectorAll("button[aria-expanded]")).toHaveLength(2);
    expect(semana2.querySelectorAll("button[aria-expanded]")).toHaveLength(1);
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

  it("el + de cada panel propone el primer día libre de esa semana", async () => {
    // La semana 1 tiene los días 1 y 2, así que le toca el 3; la 2 tiene el 1,
    // así que le toca el 2. El número sale del panel y no de un formulario
    // suelto que hay que completar dos veces.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    expect(screen.getByTitle("Agregar el día 3")).toBeInTheDocument();
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

describe("copiar y pegar semanas", () => {
  beforeEach(() => vi.unstubAllGlobals());

  const semana = (n: number) =>
    screen.getByRole("heading", { name: `Semana ${n}` }).closest("section")!;

  it("sólo ofrece copiar las semanas que tienen algo", async () => {
    // Copiar una semana vacía no significa nada, y el servidor la rechaza con
    // 404. Un botón que no puede funcionar es peor que uno que no está.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    expect(within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ })).toBeVisible();
    expect(within(semana(3)).queryByRole("button", { name: /Copiar/ })).toBeNull();
  });

  it("pegar aparece recién después de copiar, y no sobre la copiada", async () => {
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });

    expect(screen.queryByRole("button", { name: /Pegar/ })).toBeNull();

    await userEvent.click(within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ }));

    expect(within(semana(3)).getByRole("button", { name: /Pegar la semana 1/ })).toBeVisible();
    expect(within(semana(1)).queryByRole("button", { name: /Pegar/ })).toBeNull();
  });

  it("no ofrece pegar sobre una semana que ya tiene días", async () => {
    // El servidor contesta 409 para no pisar trabajo hecho — el atleta pudo
    // haber registrado series ahí. Se deshabilita antes para no ofrecer un
    // botón que contesta un error.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    await userEvent.click(within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ }));

    expect(within(semana(2)).queryByRole("button", { name: /Pegar/ })).toBeNull();
  });

  it("dice cuánto se mueve el RIR antes de apretar", async () => {
    // Es la razón por la que duplicar sirve. Decirlo después convierte una
    // decisión en una sorpresa. Progresión [0, 0, -1, -1]: de la 1 a la 3 baja
    // un punto.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    await userEvent.click(within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ }));

    expect(within(semana(3)).getByText("RIR -1")).toBeVisible();
  });

  it("pegar manda el origen y el destino correctos", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    await userEvent.click(within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ }));
    await userEvent.click(within(semana(4)).getByRole("button", { name: /Pegar la semana 1/ }));

    const alta = pedido.mock.calls.find(([u]) => String(u).includes("duplicate-week"));
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ from_week: 1, to_week: 4 });
  });

  it("volver a apretar copiar suelta lo copiado", async () => {
    // Sin esto, una vez copiada una semana no hay forma de volver atrás salvo
    // recargar, y los botones de pegar quedan puestos en toda la pantalla.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: "Semana 1" });
    const copiar = within(semana(1)).getByRole("button", { name: /Copiar la semana 1/ });

    await userEvent.click(copiar);
    await userEvent.click(within(semana(1)).getByRole("button", { name: /Soltar la semana 1/ }));

    expect(screen.queryByRole("button", { name: /Pegar/ })).toBeNull();
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
      { id: "s9", mesocycle: "Intensificación", mesocycle_ordinal: 2, week_number: 1, day_number: 1 },
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

  const bloque = (nombre: string) =>
    screen.getByRole("heading", { name: new RegExp(nombre) }).closest("section")!;

  it("con un solo bloque ofrece duplicar y no copiar", async () => {
    // Con uno solo no hay dónde pegar, así que «Copiar» sería un botón que no
    // lleva a ningún lado. Para crear el segundo está «Duplicar», de un toque.
    responder();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });

    expect(screen.getByRole("button", { name: "Duplicar" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Copiar el bloque/ })).toBeNull();
  });

  it("duplicar crea uno nuevo, sin destino", async () => {
    const pedido = responder();
    montarEditor();
    await screen.findByRole("heading", { name: /Acumulación/ });
    await userEvent.click(screen.getByRole("button", { name: "Duplicar" }));

    const alta = pedido.mock.calls.find(([u]) => String(u).includes("/duplicate"));
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ to_mesocycle: null });
  });

  it("con más de un bloque aparece copiar en todos", async () => {
    conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Intensificación/ });

    expect(screen.getAllByRole("button", { name: /Copiar el bloque/ })).toHaveLength(3);
  });

  it("pegar aparece sólo en el bloque vacío, después de copiar", async () => {
    conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Intensificación/ });

    expect(screen.queryByRole("button", { name: /Pegar el bloque/ })).toBeNull();

    await userEvent.click(
      within(bloque("Acumulación")).getByRole("button", { name: /Copiar el bloque/ }),
    );

    // Sólo «Descarga» está vacío. «Intensificación» tiene sesiones y no es el
    // copiado: es el caso que distingue si la condición existe de verdad.
    expect(within(bloque("Descarga")).getByRole("button", { name: /Pegar/ })).toBeVisible();
    expect(within(bloque("Intensificación")).queryByRole("button", { name: /Pegar/ })).toBeNull();
    expect(within(bloque("Acumulación")).queryByRole("button", { name: /Pegar/ })).toBeNull();
  });

  it("pegar manda el origen en la ruta y el destino en el cuerpo", async () => {
    const pedido = conTresBloques();
    montarEditor();
    await screen.findByRole("heading", { name: /Intensificación/ });
    await userEvent.click(
      within(bloque("Acumulación")).getByRole("button", { name: /Copiar el bloque/ }),
    );
    await userEvent.click(within(bloque("Descarga")).getByRole("button", { name: /Pegar/ }));

    const alta = pedido.mock.calls.find(
      ([u, o]) => String(u).includes("/duplicate") && o?.method === "POST",
    );
    expect(String(alta![0])).toContain("/api/mesocycles/m1/duplicate");
    expect(JSON.parse(String(alta![1]!.body))).toEqual({ to_mesocycle: "m3" });
  });
});
