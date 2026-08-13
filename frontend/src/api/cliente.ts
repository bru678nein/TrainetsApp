import { API_URL } from "../lib/entorno";

/** Los dos roles que el backend acepta. Cualquier otro es un 400. */
export type Rol = "coach" | "athlete";

export type ObtenerToken = () => Promise<string | null>;

export class SinSesion extends Error {
  constructor() {
    super("No hay token: la llamada al API se hizo fuera de una sesión iniciada.");
  }
}

/**
 * A rejection from the API, carrying the reason and not only the code.
 *
 * `detail` travels because the status is not always enough to know what to say.
 * Accepting an invitation answers `409` both when the link was already used and
 * when the person is already an athlete of that coach, and those two need
 * different sentences: one is "ask for another link", the other is "you already
 * have this". Collapsing them into "409" throws away a distinction the backend
 * went out of its way to make.
 */
export class ErrorDelApi extends Error {
  constructor(
    readonly status: number,
    readonly detalle: string | null = null,
  ) {
    super(`El API respondió ${status}${detalle ? `: ${detalle}` : ""}`);
  }
}

/**
 * The only place in this application that builds a request to the API.
 *
 * It exists for the same reason `tenant_session` does on the other side: if any
 * component can call `fetch` on its own, one of them eventually will, without
 * the `Active-Role` header, and get back a 400 that explains nothing. With one
 * door, forgetting is not possible.
 *
 * The token is asked for on every call and never held. Clerk's session tokens
 * live sixty seconds; keeping one in a variable or in React state produces
 * intermittent 401s that only appear once a tab has been open for a minute —
 * which is to say never while somebody is developing, and constantly for whoever
 * leaves the panel open while they think.
 *
 * `rol` accepts `null`, and that is not a convenience. Claiming an athlete record
 * is the one call made by somebody who holds no role yet — that is the whole
 * point of the invitation — and its endpoint reads no `Active-Role` at all.
 * Sending one anyway would assert a role the caller may not have; the server
 * ignores it, which is exactly what makes the lie easy to keep.
 */
export async function pedirAlApi(
  ruta: string,
  opciones: {
    obtenerToken: ObtenerToken;
    rol: Rol | null;
    metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    cuerpo?: unknown;
    signal?: AbortSignal;
  },
): Promise<unknown> {
  const token = await opciones.obtenerToken();
  if (!token) throw new SinSesion();

  const cabeceras: Record<string, string> = { Authorization: `Bearer ${token}` };
  // Who you are comes from the token; which role you are looking from does not,
  // and the backend refuses to guess it. A person can be a coach and somebody
  // else's athlete at the same time.
  if (opciones.rol) cabeceras["Active-Role"] = opciones.rol;
  if (opciones.cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";

  const respuesta = await fetch(`${API_URL}${ruta}`, {
    method: opciones.metodo ?? "GET",
    headers: cabeceras,
    body: opciones.cuerpo === undefined ? undefined : JSON.stringify(opciones.cuerpo),
    signal: opciones.signal,
  });

  if (!respuesta.ok) throw new ErrorDelApi(respuesta.status, await _detalle(respuesta));
  // `204 No Content` no trae cuerpo, y pedirle `json()` explota con un error de
  // parser que no tiene nada que ver con lo que pasó. Los borrados contestan así.
  if (respuesta.status === 204) return null;
  return respuesta.json();
}

/**
 * The `detail` FastAPI puts in the body, when there is one.
 *
 * Every failure here is swallowed on purpose. This runs while an error is already
 * being reported, and a body that is empty, truncated or not JSON at all — a
 * proxy's HTML error page, most of the time — must not replace a useful `502`
 * with a parser exception thrown from the catch path.
 */
async function _detalle(respuesta: Response): Promise<string | null> {
  try {
    const cuerpo = (await respuesta.json()) as { detail?: unknown };
    return typeof cuerpo.detail === "string" ? cuerpo.detail : null;
  } catch {
    return null;
  }
}
