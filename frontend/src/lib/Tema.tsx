import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import { Luna, Sol } from "../components/iconos";

/**
 * Claro u oscuro, elegido y recordado.
 *
 * El claro es el default para todo el mundo, y eso es una decisión y no un
 * olvido: antes la aplicación seguía `prefers-color-scheme`, así que se veía
 * distinta en cada máquina sin que nadie lo hubiera pedido. Ahora arranca en
 * blanco y el oscuro se pide.
 *
 * Se recuerda en `localStorage` por el mismo motivo que el rol: no es una
 * credencial, es una preferencia, y volver a elegirla en cada recarga es una
 * molestia sin contrapartida.
 *
 * Lo que pinta no es esto: es el atributo `data-tema` en el `<html>`, que el
 * CSS mira. Este módulo sólo decide qué dice ese atributo, lo cual mantiene todo
 * el color en la hoja de estilos y ninguno acá.
 */

export type Tema = "claro" | "oscuro";

const CLAVE = "tema";

function _guardado(): Tema {
  try {
    return localStorage.getItem(CLAVE) === "oscuro" ? "oscuro" : "claro";
  } catch {
    return "claro";
  }
}

type Contexto = { tema: Tema; alternar: () => void };

const TemaContext = createContext<Contexto | null>(null);

export function ProveedorDeTema({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(_guardado);

  // El atributo se escribe en un efecto y no al renderizar: tocar el `<html>`
  // durante el render es un efecto secundario fuera de React, y en modo estricto
  // corre dos veces.
  useEffect(() => {
    document.documentElement.dataset.tema = tema;
  }, [tema]);

  const alternar = useCallback(() => {
    setTema((actual) => {
      const nuevo = actual === "oscuro" ? "claro" : "oscuro";
      try {
        localStorage.setItem(CLAVE, nuevo);
      } catch {
        // Modo privado o storage lleno: vale para esta sesión igual.
      }
      return nuevo;
    });
  }, []);

  const valor = useMemo(() => ({ tema, alternar }), [tema, alternar]);
  return <TemaContext.Provider value={valor}>{children}</TemaContext.Provider>;
}

export function useTema(): Contexto {
  const valor = useContext(TemaContext);
  if (valor === null) throw new Error("useTema fuera de ProveedorDeTema");
  return valor;
}

/**
 * El interruptor.
 *
 * Muestra el ícono de **adonde va**, no el del estado actual, que es lo que
 * espera quien lo mira: un sol quiere decir «tocá para aclarar». Y lo dice
 * también con palabras, porque un ícono solo es ambiguo justamente en este
 * control — hay productos que hacen lo contrario.
 */
export function BotonDeTema() {
  const { tema, alternar } = useTema();
  const va = tema === "oscuro" ? "claro" : "oscuro";
  return (
    <button
      type="button"
      className="sutil marco__tema"
      onClick={alternar}
      aria-label={`Cambiar a modo ${va}`}
      title={`Cambiar a modo ${va}`}
    >
      {va === "oscuro" ? <Luna /> : <Sol />}
    </button>
  );
}
