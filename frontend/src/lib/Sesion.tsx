import { SignedIn, SignedOut, SignIn, UserButton } from "@clerk/clerk-react";
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
        <SignIn />
      </SignedOut>
      <SignedIn>
        <header>
          <UserButton />
        </header>
        {children}
      </SignedIn>
    </>
  );
}
