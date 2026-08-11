import { API_URL } from "../lib/entorno";

/** Los dos roles que el backend acepta. Cualquier otro es un 400. */
export type Rol = "coach" | "athlete";

export type ObtenerToken = () => Promise<string | null>;

export class SinSesion extends Error {
  constructor() {
    super("No hay token: la llamada al API se hizo fuera de una sesión iniciada.");
  }
}

export class ErrorDelApi extends Error {
  constructor(readonly status: number) {
    super(`El API respondió ${status}`);
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
 */
export async function pedirAlApi(
  ruta: string,
  opciones: { obtenerToken: ObtenerToken; rol: Rol; signal?: AbortSignal },
): Promise<unknown> {
  const token = await opciones.obtenerToken();
  if (!token) throw new SinSesion();

  const respuesta = await fetch(`${API_URL}${ruta}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      // Who you are comes from the token; which role you are looking from does
      // not, and the backend refuses to guess it. A person can be a coach and
      // somebody else's athlete at the same time.
      "Active-Role": opciones.rol,
    },
    signal: opciones.signal,
  });

  if (!respuesta.ok) throw new ErrorDelApi(respuesta.status);
  return respuesta.json();
}
