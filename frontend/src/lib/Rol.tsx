import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { Rol } from "../api/cliente";

/**
 * Desde qué rol se está mirando, elegido y no adivinado.
 *
 * El backend exige la cabecera `Active-Role` y se niega a ponerle un valor por
 * defecto, y eso no es burocracia: una persona puede ser entrenadora y, al mismo
 * tiempo, atleta de otro entrenador. Adivinar el rol es lo que convierte tener
 * dos en una forma de entrar al espacio ajeno.
 *
 * Vive en un contexto y no en cada pantalla porque el rol es de la sesión, no de
 * la vista. Dos componentes de la misma pantalla pidiendo con roles distintos
 * mostrarían dos mitades de mundos diferentes.
 *
 * Se recuerda en `localStorage` a propósito, al revés que el token de invitación:
 * esto no es una credencial, es una preferencia, y perderla en cada recarga
 * obliga a elegir de nuevo a quien casi siempre entra con el mismo sombrero.
 */

const CLAVE = "rol-activo";

function _guardado(): Rol {
  try {
    const valor = localStorage.getItem(CLAVE);
    return valor === "athlete" ? "athlete" : "coach";
  } catch {
    return "coach";
  }
}

type Contexto = { rol: Rol; cambiar: (rol: Rol) => void };

const RolContext = createContext<Contexto | null>(null);

export function ProveedorDeRol({ children }: { children: ReactNode }) {
  const [rol, setRol] = useState<Rol>(_guardado);
  const cambiar = useCallback((nuevo: Rol) => {
    setRol(nuevo);
    try {
      localStorage.setItem(CLAVE, nuevo);
    } catch {
      // Modo privado o storage lleno: la elección vale para esta sesión igual.
    }
  }, []);
  const valor = useMemo(() => ({ rol, cambiar }), [rol, cambiar]);
  return <RolContext.Provider value={valor}>{children}</RolContext.Provider>;
}

export function useRol(): Contexto {
  const ctx = useContext(RolContext);
  if (!ctx) throw new Error("useRol fuera de ProveedorDeRol");
  return ctx;
}

/** El interruptor, que en un MVP es lo mínimo que hace usable tener dos roles. */
export function SelectorDeRol() {
  const { rol, cambiar } = useRol();
  return (
    <label>
      Estoy mirando como{" "}
      <select value={rol} onChange={(e) => cambiar(e.target.value as Rol)}>
        <option value="coach">entrenador</option>
        <option value="athlete">atleta</option>
      </select>
    </label>
  );
}
