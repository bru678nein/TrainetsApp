import { Link, Route, Routes } from "react-router-dom";

import { ListadoDeAtletas } from "./features/atletas/ListadoDeAtletas";
import { Editor } from "./features/editor/Editor";
import { MisSesiones, SesionDelDia } from "./features/entrenar/Entrenar";
import { PanelDelAtleta } from "./features/analytics/PanelDelAtleta";
import { Aceptar } from "./features/invitaciones/Aceptar";

/**
 * Routes, and the reason there is a router at all for two screens.
 *
 * The athlete's panel needs an address. A panel that cannot be linked is a panel
 * that gets shared as a screenshot, and reloading the page has to land back on
 * the same athlete rather than at the top — which is what happens when the
 * selected athlete lives in component state instead of in the URL.
 */
export function Rutas() {
  return (
    <Routes>
      <Route path="/" element={<ListadoDeAtletas />} />
      <Route path="/atletas/:atletaId" element={<PanelDelAtleta />} />
      <Route path="/atletas/:atletaId/programa" element={<Editor />} />
      <Route path="/entrenar" element={<MisSesiones />} />
      <Route path="/entrenar/:sesionId" element={<SesionDelDia />} />
      {/* El token viaja en la ruta y no en la query: una query string se pierde
          en más redirecciones, y ésta atraviesa la del proveedor de identidad. */}
      <Route path="/invitacion/:token" element={<Aceptar />} />
      <Route
        path="*"
        element={
          <section>
            <h2>Esa página no existe</h2>
            <Link to="/">Volver a los atletas</Link>
          </section>
        }
      />
    </Routes>
  );
}
