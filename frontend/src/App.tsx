import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { Marco } from "./lib/Marco";
import { ProveedorDeRol } from "./lib/Rol";
import { Sesion } from "./lib/Sesion";
import { Rutas } from "./rutas";

/**
 * `retry: false` because the failures worth showing here are not transient.
 *
 * A 401 or a 403 will answer the same way three times over while the interface
 * shows a spinner that never resolves, and what is wanted is an error state, not
 * for patience. What retrying does buy — surviving a dropped connection — is not
 * what breaks in practice with this API.
 */
const cliente = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <QueryClientProvider client={cliente}>
      <BrowserRouter>
        <ProveedorDeRol>
          <Sesion>
            <Marco>
              <Rutas />
            </Marco>
          </Sesion>
        </ProveedorDeRol>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
