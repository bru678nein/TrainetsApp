import { useAuth } from "@clerk/clerk-react";
import { useCallback } from "react";

import { useRol } from "../lib/Rol";
import { pedirAlApi, type Rol } from "./cliente";

/**
 * The wrapper bound to the current session.
 *
 * `getToken` is passed down rather than called here: the rule that the token is
 * fetched per request lives in `pedirAlApi`, and testing it there needs no React
 * and no Clerk.
 */
export function useApi(forzado?: Rol) {
  const { getToken } = useAuth();
  // El rol sale del contexto salvo que la pantalla imponga uno. Lo imponen las
  // que sólo tienen sentido desde un lado —el editor es del entrenador, la
  // agenda de hoy es del atleta— para que el interruptor no las rompa.
  const { rol: activo } = useRol();
  const rol = forzado ?? activo;
  return useCallback(
    (ruta: string, signal?: AbortSignal) =>
      pedirAlApi(ruta, { obtenerToken: () => getToken(), rol, signal }),
    [getToken, rol],
  );
}

/**
 * The same door, for the calls that write.
 *
 * Separate from `useApi` rather than a flag on it, because a reader and a writer
 * are used differently — one is handed to `useQuery` and runs on mount, the other
 * to `useMutation` and runs when somebody presses something. Giving them the same
 * signature invites passing the writer where the reader goes, which is a POST on
 * every render.
 *
 * `rol` is `Rol | null` for the reason spelled out in `pedirAlApi`: whoever
 * claims a record holds no role yet.
 */
export function useEnviar(forzado?: Rol | null) {
  const { getToken } = useAuth();
  const { rol: activo } = useRol();
  const rol = forzado === undefined ? activo : forzado;
  return useCallback(
    (ruta: string, cuerpo?: unknown) =>
      pedirAlApi(ruta, { obtenerToken: () => getToken(), rol, metodo: "POST", cuerpo }),
    [getToken, rol],
  );
}

/**
 * Las escrituras que no son altas: corregir, reordenar y borrar.
 *
 * Un solo hook para los tres verbos en vez de uno por verbo. Lo que cambia entre
 * ellos es una palabra, y tres hooks idénticos serían tres lugares donde
 * arreglar lo mismo.
 */
export function useMutar(forzado?: Rol) {
  const { getToken } = useAuth();
  const { rol: activo } = useRol();
  const rol = forzado ?? activo;
  return useCallback(
    (metodo: "PUT" | "PATCH" | "DELETE", ruta: string, cuerpo?: unknown) =>
      pedirAlApi(ruta, { obtenerToken: () => getToken(), rol, metodo, cuerpo }),
    [getToken, rol],
  );
}
