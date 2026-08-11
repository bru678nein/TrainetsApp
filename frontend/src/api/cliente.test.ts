import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { ErrorDelApi, SinSesion, pedirAlApi, type ObtenerToken } from "./cliente";

/**
 * Este archivo es el equivalente frontend del recorrido de rutas del backend:
 * protege reglas que se rompen por olvido y no por error, y cuyo síntoma no se
 * ve mirando la pantalla.
 *
 * Sin `Authorization` la respuesta es 401. Sin `Active-Role` es 400. Las dos se
 * leen como "algo del backend anda mal".
 */

function respuestaOk() {
  return Promise.resolve(new Response("[]", { status: 200 }));
}

function cabeceras(): Headers {
  const llamada = vi.mocked(fetch).mock.calls[0];
  return new Headers(llamada?.[1]?.headers);
}

describe("la única puerta al API", () => {
  let obtenerToken: Mock<ObtenerToken>;

  beforeEach(() => {
    obtenerToken = vi.fn<ObtenerToken>(() => Promise.resolve("un-token"));
    vi.stubGlobal("fetch", vi.fn(respuestaOk));
  });

  describe("las dos cabeceras", () => {
    it("manda el token en Authorization", async () => {
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      expect(cabeceras().get("Authorization")).toBe("Bearer un-token");
    });

    it("manda el rol activo en Active-Role", async () => {
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      expect(cabeceras().get("Active-Role")).toBe("coach");
    });

    it("el rol es el que se pide, no uno fijo", async () => {
      // El control. Sin esto, un "coach" hardcodeado pasaría el test de arriba y
      // la app del atleta nunca vería sus propios datos.
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "athlete" });
      expect(cabeceras().get("Active-Role")).toBe("athlete");
    });
  });

  describe("el token se pide en cada llamada", () => {
    it("dos requests piden el token dos veces", async () => {
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      expect(obtenerToken).toHaveBeenCalledTimes(2);
    });

    it("un token renovado se usa, no queda el viejo", async () => {
      // Los de Clerk viven 60 segundos. Guardarlo produce 401 que sólo aparecen
      // con una pestaña abierta un rato: nunca mientras uno desarrolla, siempre
      // para quien deja el panel abierto mientras piensa.
      obtenerToken
        .mockResolvedValueOnce("token-viejo")
        .mockResolvedValueOnce("token-renovado");

      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });

      const segunda = vi.mocked(fetch).mock.calls[1];
      expect(new Headers(segunda?.[1]?.headers).get("Authorization")).toBe("Bearer token-renovado");
    });
  });

  describe("cuándo no llama", () => {
    it("sin token no toca la red", async () => {
      obtenerToken.mockResolvedValue(null);
      await expect(pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" })).rejects.toThrow(
        SinSesion,
      );
      expect(fetch).not.toHaveBeenCalled();
    });
  });

  describe("qué hace con una respuesta que no sirve", () => {
    it("un 403 no se devuelve como datos", async () => {
      // Sin esto, `respuesta.json()` sobre un cuerpo de error devuelve un objeto
      // y la vista dibuja un panel vacío en vez de decir que algo falló.
      vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 403 }));
      await expect(pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" })).rejects.toThrow(
        ErrorDelApi,
      );
    });
  });

  describe("a dónde llama", () => {
    it("usa la base del API y no una ruta relativa", async () => {
      // Relativa apuntaría al servidor de Vite, que no tiene ningún /api y
      // devuelve el index.html: un 200 con HTML adentro, que es peor que un error.
      await pedirAlApi("/api/athletes", { obtenerToken, rol: "coach" });
      expect(vi.mocked(fetch).mock.calls[0]?.[0]).toContain("/api/athletes");
      expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toMatch(/^https?:\/\//);
    });
  });
});
