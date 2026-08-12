import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { montar } from "../../lib/pruebas";
import { Aceptar } from "./Aceptar";
import { guardar, recuperar } from "./tokenEnTransito";

/** Ver la nota en `Invitar.test.tsx`: acá corre el cliente de verdad. */
vi.mock("@clerk/clerk-react", () => ({
  useAuth: () => ({ getToken: () => Promise.resolve("un-token") }),
}));

const RUTA = "/invitacion/tok-abc";

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

/**
 * Montada dentro de su ruta y no suelta, porque `useParams` sólo devuelve algo
 * cuando el componente cuelga de un `path` con el segmento declarado. Suelta, el
 * token siempre falta y los tests pasarían mirando la pantalla equivocada.
 */
function montarEnRuta(ruta: string) {
  return montar(
    <Routes>
      <Route path="/invitacion/:token" element={<Aceptar />} />
      <Route path="/invitacion" element={<Aceptar />} />
    </Routes>,
    ruta,
  );
}

describe("aceptar la invitación", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("manda el token que venía en la URL", async () => {
    const pedido = responder(200, { resultado: "aceptada" });
    montarEnRuta(RUTA);
    await screen.findByText(/ya estás asociado/i);

    const { url, opciones } = llamada(pedido);
    expect(url).toContain("/api/me/invitation");
    expect(opciones.method).toBe("POST");
    expect(JSON.parse(String(opciones.body))).toEqual({ token: "tok-abc" });
  });

  it("no manda ningún rol", async () => {
    // Quien acepta todavía no es atleta de nadie: el endpoint no lee
    // `Active-Role` y mandarlo afirmaría un rol que la persona no tiene. Es la
    // única llamada de la aplicación que sale sin esa cabecera.
    const pedido = responder(200, { resultado: "aceptada" });
    montarEnRuta(RUTA);
    await screen.findByText(/ya estás asociado/i);

    const { opciones } = llamada(pedido);
    expect(new Headers(opciones.headers).has("Active-Role")).toBe(false);
    expect(new Headers(opciones.headers).get("Authorization")).toBe("Bearer un-token");
  });

  it("lo manda una sola vez", async () => {
    // Un link es de un solo uso. React monta dos veces en desarrollo, y sin la
    // guarda el segundo envío contesta `invitacion_usada` sobre la invitación
    // que el primero acababa de consumir: el atleta ve un error habiendo entrado.
    const pedido = responder(200, { resultado: "aceptada" });
    montarEnRuta(RUTA);
    await screen.findByText(/ya estás asociado/i);
    expect(pedido).toHaveBeenCalledTimes(1);
  });
});

describe("el token sobrevive al login del proveedor", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("si el proveedor devolvió el navegador sin el token, se usa el guardado", async () => {
    // Éste es el caso para el que existe el módulo de tránsito: el atleta abrió
    // el link sin sesión, el proveedor lo devolvió a otra dirección, y el token
    // ya no está en la barra. Sin esto el link se gastó sin usarse, y sólo el
    // entrenador puede generar otro.
    const pedido = responder(200, { resultado: "aceptada" });
    guardar("tok-guardado");
    montarEnRuta("/invitacion");
    await screen.findByText(/ya estás asociado/i);

    const { opciones } = llamada(pedido);
    expect(JSON.parse(String(opciones.body))).toEqual({ token: "tok-guardado" });
  });

  it("se borra cuando ya hay respuesta", async () => {
    responder(200, { resultado: "aceptada" });
    montarEnRuta(RUTA);
    await screen.findByText(/ya estás asociado/i);
    expect(recuperar()).toBeNull();
  });

  it("también se borra cuando el servidor rechaza", async () => {
    // Un token rechazado está gastado o es inválido. Dejarlo guardado hace que
    // la próxima visita reintente una llamada que no puede salir bien.
    guardar("tok-abc");
    responder(410, { detail: "invitacion_vencida" });
    montarEnRuta(RUTA);
    await screen.findByRole("alert");
    expect(recuperar()).toBeNull();
  });

  it("sin token en ningún lado, dice qué hacer y no llama al API", () => {
    const pedido = responder(200, {});
    montarEnRuta("/invitacion");
    expect(screen.getByText(/Falta el link/i)).toBeInTheDocument();
    expect(pedido).not.toHaveBeenCalled();
  });
});

describe("cada rechazo dice algo distinto", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  const CASOS: [number, string, RegExp][] = [
    [404, "invitacion_inexistente", /no existe/i],
    [410, "invitacion_vencida", /venció/i],
    [409, "invitacion_usada", /ya se usó/i],
    [409, "ya_sos_atleta_de_ese_entrenador", /ya sos atleta/i],
    [410, "vinculo_archivado", /cerró este vínculo/i],
  ];

  it.each(CASOS)("%s %s", async (estado, detalle, esperado) => {
    // El backend se toma el trabajo de distinguir seis resultados, y dos de
    // ellos comparten el `409`. Si acá se colapsaran en "no se pudo", ese
    // trabajo no llega a la persona que tiene que decidir qué hacer.
    responder(estado, { detail: detalle });
    montarEnRuta(RUTA);
    expect(await screen.findByRole("alert")).toHaveTextContent(esperado);
  });

  it("un error que no es del ciclo no se disfraza de uno que sí", async () => {
    // Decir "el link venció" ante un 500 manda a pedir otro link que tampoco va
    // a funcionar.
    responder(500, { detail: "algo interno" });
    montarEnRuta(RUTA);
    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo aceptar/i);
  });

  it("un cuerpo que no es JSON no tapa el error con una excepción del parser", async () => {
    // Un proxy caído contesta HTML. Leer el `detail` corre dentro del camino de
    // error, así que si explotara ahí reemplazaría un 502 legible por un fallo
    // del parser.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("<html>502</html>", { status: 502 }))),
    );
    montarEnRuta(RUTA);
    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo aceptar/i);
  });
});
