import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const raiz = document.getElementById("root");
// Explicit and not `!`: a missing root means index.html and this file disagree,
// and a silent null gives a blank page with nothing in the console.
if (!raiz) throw new Error("Falta el elemento #root en index.html");

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
