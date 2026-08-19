/**
 * «Hace 2 días», que es como se lee un abandono.
 *
 * Una fecha absoluta obliga a restar mentalmente contra hoy, y el entrenador
 * mira este listado para detectar quién se está cayendo — la pregunta es cuánto
 * hace, no qué día fue.
 *
 * Pasado el mes vuelve a la fecha: «hace 47 días» ya no dice nada que «12 de
 * julio» no diga mejor, y a esa altura la persona no se está cayendo, se cayó.
 */
export function hace(iso: string | null | undefined, ahora = new Date()): string {
  if (!iso) return "nunca";
  const cuando = new Date(iso);
  const dias = Math.floor((ahora.getTime() - cuando.getTime()) / 86_400_000);
  if (dias <= 0) return "hoy";
  if (dias === 1) return "ayer";
  if (dias <= 30) return `hace ${dias} días`;
  return cuando.toLocaleDateString("es-AR", { day: "numeric", month: "short", year: "numeric" });
}

/** Cuántos días hace, para decidir si hay que avisar. `null` si nunca entrenó. */
export function diasDesde(iso: string | null | undefined, ahora = new Date()): number | null {
  if (!iso) return null;
  return Math.floor((ahora.getTime() - new Date(iso).getTime()) / 86_400_000);
}
