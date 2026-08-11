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
