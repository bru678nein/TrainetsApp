import { Link, useParams } from "react-router-dom";

import { Adherencia } from "./Adherencia";

export function PanelDelAtleta() {
  const { atletaId } = useParams();
  if (!atletaId) return null;

  return (
    <>
      <p>
        <Link to="/">← Atletas</Link>
      </p>
      <Adherencia atletaId={atletaId} />
    </>
  );
}
