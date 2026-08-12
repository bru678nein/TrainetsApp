import { ClerkProvider } from "@clerk/clerk-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./estilos.css";
import { capturarDeLaUrl } from "./features/invitaciones/tokenEnTransito";
import { CLERK_PUBLISHABLE_KEY } from "./lib/entorno";

// Antes de que React monte nada, y sobre todo antes de que el portón de sesión
// pueda reemplazar la pantalla por el formulario del proveedor: si esta carga
// trae un token de invitación en la dirección, se guarda ahora. Después del
// login la dirección puede no ser la misma, y un link de un solo uso que se
// pierde no lo puede regenerar quien lo recibió.
capturarDeLaUrl();

const raiz = document.getElementById("root");
// Explicit and not `!`: a missing root means index.html and this file disagree,
// and a silent null gives a blank page with nothing in the console.
if (!raiz) throw new Error("Falta el elemento #root en index.html");

createRoot(raiz).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>
      <App />
    </ClerkProvider>
  </StrictMode>,
);
