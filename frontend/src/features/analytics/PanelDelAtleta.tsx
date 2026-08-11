import { useParams } from "react-router-dom";

export function PanelDelAtleta() {
  const { atletaId } = useParams();
  return <h2>Panel de {atletaId}</h2>;
}
