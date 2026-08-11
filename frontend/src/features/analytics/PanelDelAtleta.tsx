import { Link, useParams } from "react-router-dom";

import { Adherencia } from "./Adherencia";
import { Volumen } from "./Volumen";

export function PanelDelAtleta() {
  const { atletaId } = useParams();
  if (!atletaId) return null;

  return (
    <>
      <p>
        <Link to="/">← Atletas</Link>
      </p>
      <Adherencia atletaId={atletaId} />
      <Volumen atletaId={atletaId} />
    </>
  );
}
