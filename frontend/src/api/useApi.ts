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
