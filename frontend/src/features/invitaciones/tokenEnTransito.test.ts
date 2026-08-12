import { beforeEach, describe, expect, it, vi } from "vitest";

import { capturarDeLaUrl, guardar, olvidar, recuperar } from "./tokenEnTransito";

describe("el token sobrevive al ida y vuelta del login", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("lo que se guarda se recupera", () => {
    guardar("tok-abc");
    expect(recuperar()).toBe("tok-abc");
  });

  it("sin nada guardado devuelve null y no rompe", () => {
    expect(recuperar()).toBeNull();
  });

  it("olvidar lo saca", () => {
    guardar("tok-abc");
    olvidar();
    expect(recuperar()).toBeNull();
  });

  it("vive en sessionStorage, que muere con la pestaña", () => {
    // Un token de un solo uso no tiene por qué sobrevivir a la pestaña que lo
    // recibió, y en una computadora compartida —un gimnasio— eso importa.
    // Se afirma sobre `sessionStorage` y no sobre la ausencia en `localStorage`
    // porque este Node no expone el segundo, y un test que no puede fallar no
    // dice nada.
    guardar("tok-abc");
    expect(sessionStorage.getItem("invitacion:token")).toBe("tok-abc");
  });
});

describe("un almacenamiento que falla no voltea la pantalla", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("guardar no propaga la excepción", () => {
    // Modo privado, cuota llena, storage deshabilitado: todos tiran acá. Si esto
    // propagara, el atleta vería una pantalla en blanco en vez de su invitación.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    expect(() => guardar("tok-abc")).not.toThrow();
  });

  it("recuperar devuelve null en vez de explotar", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    expect(recuperar()).toBeNull();
  });

  it("olvidar tampoco", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("SecurityError");
    });
    expect(() => olvidar()).not.toThrow();
  });
});

describe("capturar de la dirección, que es lo que corre antes del portón", () => {
  beforeEach(() => sessionStorage.clear());

  it("saca el token de /invitacion/<token> y lo guarda", () => {
    expect(capturarDeLaUrl("/invitacion/tok-abc")).toBe("tok-abc");
    expect(recuperar()).toBe("tok-abc");
  });

  it("no toca nada en cualquier otra dirección", () => {
    guardar("anterior");
    expect(capturarDeLaUrl("/atletas/a1")).toBeNull();
    expect(recuperar()).toBe("anterior");
  });

  it("ignora la barra final y lo que venga después", () => {
    expect(capturarDeLaUrl("/invitacion/tok-abc/")).toBe("tok-abc");
  });

  it("decodifica lo que el navegador escapó", () => {
    expect(capturarDeLaUrl("/invitacion/tok%2Babc")).toBe("tok+abc");
  });

  it("una ruta sin token no guarda una cadena vacía", () => {
    // `/invitacion` sin nada es la pantalla que dice "falta el link". Guardar ""
    // acá haría que la próxima visita creyera tener uno.
    expect(capturarDeLaUrl("/invitacion")).toBeNull();
    expect(recuperar()).toBeNull();
  });
});
