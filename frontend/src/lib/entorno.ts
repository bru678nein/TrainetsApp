/**
 * Configuration read once, and loudly when it is missing.
 *
 * Vite replaces `import.meta.env` at build time, so a missing value is not an
 * undefined that shows up later — it is an undefined baked into the bundle. The
 * check has to happen somewhere, and doing it here means it happens once, at
 * startup, instead of as a blank screen with nothing in the console.
 */

function requerida(nombre: string, valor: string | undefined): string {
  if (!valor) {
    throw new Error(
      `Falta ${nombre}. Copiá .env.example a .env y completalo desde el panel de Clerk.`,
    );
  }
  return valor;
}

export const CLERK_PUBLISHABLE_KEY = requerida(
  "VITE_CLERK_PUBLISHABLE_KEY",
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
);

export const API_URL = requerida(
  "VITE_API_URL",
  import.meta.env.VITE_API_URL,
);

/**
 * Si se muestra el interruptor de rol, que por defecto no se muestra.
 *
 * No es una preferencia estética: el rol se resuelve solo. Aceptar una
 * invitación deja el rol en atleta, y un 403 sobre el espacio del entrenador
 * lleva a atleta a quien tenga fichas. Con eso, para casi todo el mundo no hay
 * nada que elegir, y un desplegable que pregunta «¿estás mirando como
 * entrenador o como atleta?» sólo confunde a quien es una sola de las dos.
 *
 * Queda para quien tiene los **dos** roles de verdad —un entrenador que además
 * es atleta de otro—, que hoy es un caso que no se puede resolver solo. Ese día
 * esto se prende, o se muestra según lo que la persona tenga.
 */
export const MOSTRAR_SELECTOR_DE_ROL = import.meta.env.VITE_MOSTRAR_SELECTOR_DE_ROL === "true";
