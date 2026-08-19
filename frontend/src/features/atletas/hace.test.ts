import { describe, expect, it } from "vitest";

import { diasDesde, hace } from "./hace";

const AHORA = new Date("2026-08-19T12:00:00Z");
const haceDias = (n: number) => new Date(AHORA.getTime() - n * 86_400_000).toISOString();

describe("hace cuánto entrenó", () => {
  it("nunca no es hace mucho", () => {
    // La diferencia importa: una ficha recién cargada no es alguien que
    // abandonó, y ofrecerle el mismo aviso al entrenador sería ruido.
    expect(hace(null, AHORA)).toBe("nunca");
    expect(diasDesde(null, AHORA)).toBeNull();
  });

  it("hoy y ayer se dicen con palabras", () => {
    expect(hace(haceDias(0), AHORA)).toBe("hoy");
    expect(hace(haceDias(1), AHORA)).toBe("ayer");
  });

  it("hasta un mes cuenta días", () => {
    expect(hace(haceDias(2), AHORA)).toBe("hace 2 días");
    expect(hace(haceDias(30), AHORA)).toBe("hace 30 días");
  });

  it("pasado el mes vuelve a la fecha", () => {
    // «hace 47 días» no dice nada que la fecha no diga mejor, y a esa altura la
    // persona no se está cayendo: se cayó.
    expect(hace(haceDias(47), AHORA)).not.toMatch(/hace/);
    expect(hace(haceDias(47), AHORA)).toMatch(/2026/);
  });

  it("cuenta los días para poder avisar", () => {
    expect(diasDesde(haceDias(14), AHORA)).toBe(14);
  });
});
