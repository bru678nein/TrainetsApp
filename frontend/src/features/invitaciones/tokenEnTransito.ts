/**
 * The invitation token, kept alive across the sign-in round trip.
 *
 * The athlete opens the link without a session. The gate renders the provider's
 * sign-in form instead of the application, and once it succeeds the provider may
 * land the browser on its configured URL rather than the one that was asked for.
 * The token is then gone from the address bar and the link has been spent on
 * nothing — and the person who lost it cannot reissue it. Only the coach can.
 *
 * The capture cannot live in the screen that consumes the token: that screen is
 * inside the gate, so it does not mount at all until there is a session, which
 * is precisely after the moment the address may have been lost. It has to happen
 * at load, before React decides anything. `capturarDeLaUrl` is called from the
 * entry point for that reason.
 *
 * `sessionStorage` and not `localStorage`: the token is a single-use credential
 * and should not outlive the tab that received it. A shared computer at a gym is
 * the normal case here, not the exotic one.
 */

const CLAVE = "invitacion:token";

/** `/invitacion/<token>`, which is the only address that carries one. */
const EN_LA_RUTA = /^\/invitacion\/([^/?#]+)/;

/**
 * Reads the token out of the current address, if this load carries one.
 *
 * Runs at load and not on navigation: the round trip that loses the address is a
 * full page load, and an in-app navigation to this route never lost anything to
 * begin with.
 */
export function capturarDeLaUrl(ruta: string = window.location.pathname): string | null {
  const encontrado = EN_LA_RUTA.exec(ruta);
  if (!encontrado?.[1]) return null;
  const token = decodeURIComponent(encontrado[1]);
  guardar(token);
  return token;
}

/** Anything can throw here: private mode, a disabled storage, a full quota. */
function _seguro<T>(accion: () => T, siFalla: T): T {
  try {
    return accion();
  } catch {
    return siFalla;
  }
}

export function guardar(token: string): void {
  _seguro(() => sessionStorage.setItem(CLAVE, token), undefined);
}

export function recuperar(): string | null {
  return _seguro(() => sessionStorage.getItem(CLAVE), null);
}

/**
 * Cleared once the answer is known, whatever the answer was.
 *
 * Not only on success: a token the server rejected is spent or invalid, and
 * leaving it behind means the next visit to the panel retries a call that cannot
 * succeed and reports an error nobody asked for.
 */
export function olvidar(): void {
  _seguro(() => sessionStorage.removeItem(CLAVE), undefined);
}
