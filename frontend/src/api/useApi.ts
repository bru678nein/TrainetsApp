import { useAuth } from "@clerk/clerk-react";
import { useCallback } from "react";

import { pedirAlApi, type Rol } from "./cliente";

/**
 * The wrapper bound to the current session.
 *
 * `getToken` is passed down rather than called here: the rule that the token is
 * fetched per request lives in `pedirAlApi`, and testing it there needs no React
 * and no Clerk.
 */
export function useApi(rol: Rol = "coach") {
  const { getToken } = useAuth();
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
export function useEnviar(rol: Rol | null = "coach") {
  const { getToken } = useAuth();
  return useCallback(
    (ruta: string, cuerpo?: unknown) =>
      pedirAlApi(ruta, { obtenerToken: () => getToken(), rol, metodo: "POST", cuerpo }),
    [getToken, rol],
  );
}
