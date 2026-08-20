import { RedirectToSignIn, SignedIn, SignedOut, SignIn, SignUp } from "@clerk/clerk-react";
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
 *
 * Signed out it now REDIRECTS instead of drawing the form in place. Rendering
 * the form over whatever address you asked for left signing in and signing up
 * with no address of their own: nothing to send somebody, nothing to link from
 * a landing page, and no way to reach the sign-up form at all — Clerk's own
 * "create an account" link had nowhere to go.
 *
 * The redirect keeps where you were headed, so an invitation link still lands on
 * the invitation after signing in.
 */
export function Sesion({ children }: { children: ReactNode }) {
  return (
    <>
      <SignedOut>
        <RedirectToSignIn />
      </SignedOut>
      <SignedIn>{children}</SignedIn>
    </>
  );
}

/**
 * Las dos pantallas de acceso, cada una con su dirección.
 *
 * `routing="path"` y no el modo por defecto: Clerk navega a subrutas propias
 * para los pasos de un ingreso —el segundo factor, la vuelta de un proveedor
 * externo—, y sin esto esos pasos no tienen dónde vivir. Por eso las rutas se
 * declaran con `/*`.
 */
export function Entrar() {
  return (
    <div className="portada">
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </div>
  );
}

export function Registrarse() {
  return (
    <div className="portada">
      <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />
    </div>
  );
}
