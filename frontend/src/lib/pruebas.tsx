import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { ProveedorDeRol } from "./Rol";

/**
 * Monta un componente con lo que necesita para vivir: rutas y un cliente de
 * consultas nuevo por test.
 *
 * Nuevo por test y no compartido: un cliente reusado guarda la respuesta de la
 * prueba anterior en caché, y el segundo test pasa mirando datos del primero.
 * Es el tipo de contaminación que aparece recién cuando alguien cambia el orden
 * de los tests.
 */
export function montar(elemento: ReactElement, ruta = "/") {
  const cliente = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const Envoltorio = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={cliente}>
      {/* El rol activo es parte de lo que un componente necesita para vivir,
          igual que el router: sin él, `useApi` no sabe qué `Active-Role` mandar
          y el backend se niega a adivinarlo. */}
      <ProveedorDeRol>
        <MemoryRouter initialEntries={[ruta]}>{children}</MemoryRouter>
      </ProveedorDeRol>
    </QueryClientProvider>
  );
  return render(elemento, { wrapper: Envoltorio });
}
