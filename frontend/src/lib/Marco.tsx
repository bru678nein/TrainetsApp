import { UserButton } from "@clerk/clerk-react";
import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

import { MOSTRAR_SELECTOR_DE_ROL } from "./entorno";
import { SelectorDeRol, useRol } from "./Rol";

/**
 * La barra y el ancho de la página, separados del portón de sesión.
 *
 * Estaban juntos y son cosas distintas: el portón decide **si** se muestra algo,
 * el marco decide **cómo se ubica**. Mezclarlos hacía que el test del portón
 * tuviera que saber de encabezados.
 *
 * La navegación cambia con el rol y no sólo la pantalla de entrada. Un atleta no
 * tiene atletas, y ofrecerle un enlace que lo lleva a una lista vacía o a un 403
 * es prometer algo que no existe.
 */
export function Marco({ children }: { children: ReactNode }) {
  const { rol } = useRol();

  return (
    <>
      <header className="marco__barra">
        <NavLink to="/" className="marco__marca">
          Trainets
        </NavLink>
        {/* `NavLink` marca la ruta activa solo; se usa acá para que la pastilla
            se vea hundida cuando ya estás en esa pantalla, en vez de invitarte a
            ir adonde ya estás. */}
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `marco__enlace${isActive ? " marco__enlace--activo" : ""}`
          }
        >
          {rol === "athlete" ? "Mis sesiones" : "Atletas"}
        </NavLink>
        {MOSTRAR_SELECTOR_DE_ROL ? <SelectorDeRol /> : null}
        <UserButton />
      </header>
      <main className="marco__contenido">{children}</main>
    </>
  );
}
