import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import type { ReactNode } from "react";

/**
 * The gate. Nothing that talks to the API renders outside it.
 *
 * `SignedIn` is not decoration: children of a component are evaluated before it
 * decides whether to render them, but they are not *mounted*, and mounting is
 * what fires a data request. Putting the panel inside this is what guarantees
 * the application does not call `/api` before it holds a token — and a call
 * without one answers 401, which teaches whoever is watching the console that
 * 401s are normal here.
 */
export function Sesion({ children }: { children: ReactNode }) {
  return (
    <>
      <SignedOut>
        {/* Centrado acá y no en el marco: el marco vive adentro del portón, así
            que la pantalla de ingreso —que es la primera que ve cualquiera— se
            quedaba sin ninguna maquetación, pegada a la esquina. */}
        <div className="portada">
          <SignIn />
        </div>
      </SignedOut>
      <SignedIn>{children}</SignedIn>
    </>
  );
}
