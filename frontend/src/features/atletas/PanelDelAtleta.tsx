import { Link, useParams } from "react-router-dom";

import { Pestanas } from "../../components/Pestanas";
import { Adherencia } from "../analytics/Adherencia";
import { Progresion } from "../analytics/Progresion";
import { Volumen } from "../analytics/Volumen";
import { Catalogo, Rutina } from "../editor/Editor";
import { Invitar } from "../invitaciones/Invitar";

/**
 * Todo lo de un atleta en una sola dirección, repartido en pestañas.
 *
 * Antes eran dos pantallas: las gráficas acá y el editor en `/programa`. Son la
 * misma conversación —armar el bloque, mirar si se está cumpliendo, corregir— y
 * tenerlas separadas obligaba a ir y volver para hacer una sola cosa.
 *
 * La rutina va primera porque es lo que se hace más seguido. Las gráficas
 * segundas: se miran para decidir qué cambiar en la rutina, así que conviene que
 * estén al lado. El catálogo y la invitación son mantenimiento y van al final.
 */
export function PanelDelAtleta() {
  const { atletaId } = useParams();
  if (!atletaId) return null;

  return (
    <>
      <p>
        <Link to="/">← Atletas</Link>
      </p>
      <Pestanas
        pestanas={[
          { id: "rutina", titulo: "Rutina", contenido: <Rutina atletaId={atletaId} /> },
          {
            id: "graficas",
            titulo: "Gráficas",
            contenido: (
              <>
                <Adherencia atletaId={atletaId} />
                <Volumen atletaId={atletaId} />
                <Progresion atletaId={atletaId} />
              </>
            ),
          },
          { id: "ejercicios", titulo: "Ejercicios", contenido: <Catalogo /> },
          {
            id: "invitacion",
            titulo: "Invitación",
            contenido: <Invitar atletaId={atletaId} />,
          },
        ]}
      />
    </>
  );
}
