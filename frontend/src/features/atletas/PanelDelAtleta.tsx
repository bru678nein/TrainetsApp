import { Link, useParams } from "react-router-dom";

import { useAtletas } from "../../api/consultas";
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
  // Sale del listado, que ya está en caché: entrar acá es venir de ahí. Un
  // endpoint por ficha para repetir un nombre que la pantalla anterior ya trajo
  // es un viaje de más en la pantalla que más se abre.
  const atletas = useAtletas();
  const atleta = atletas.data?.find((a) => a.id === atletaId);
  if (!atletaId) return null;

  return (
    <>
      <p>
        <Link to="/">← Atletas</Link>
      </p>
      {/* De quién es esto.

          El panel no lo decía en ningún lado: se entraba al editor desde una
          lista y a partir de ahí no había forma de saber a quién le estabas
          armando la rutina. Con cinco niveles abajo —programa, bloque, semana,
          día, serie— es el ancla de todo lo demás.

          Se dibuja aunque el listado todavía no haya llegado: el hueco reservado
          evita que las pestañas salten cuando el nombre aparece. */}
      <div className="panel__quien">
        <h2>{atleta?.full_name ?? "\u00a0"}</h2>
        {atleta ? (
          <>
            <span className={`chip chip--${atleta.estado ?? "activo"}`}>
              <i className="chip__punto" aria-hidden="true" />
              {atleta.estado ?? "activo"}
            </span>
            {atleta.programa_actual ? (
              <span className="panel__contexto">
                {atleta.programa_actual}
                {atleta.semana_actual && atleta.semanas_del_bloque ? (
                  <span className="numeros">
                    {" · "}semana {atleta.semana_actual} de{" "}
                    {atleta.semanas_del_bloque}
                  </span>
                ) : null}
              </span>
            ) : null}
          </>
        ) : null}
      </div>
      <Pestanas
        pestanas={[
          {
            id: "rutina",
            titulo: "Rutina",
            contenido: <Rutina atletaId={atletaId} />,
          },
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
            titulo: "Link para atleta",
            contenido: <Invitar atletaId={atletaId} />,
          },
        ]}
      />
    </>
  );
}
