import { Link } from "react-router-dom";

import { useAtletas } from "../../api/consultas";
import { Consulta } from "../../components/estados";

export function ListadoDeAtletas() {
  const consulta = useAtletas();

  return (
    <section>
      <h2>Atletas</h2>
      <Consulta
        consulta={consulta}
        que="los atletas"
        vacio={{
          cuando: (atletas) => atletas.length === 0,
          motivo: "Todavía no cargaste ningún atleta.",
        }}
      >
        {(atletas) => (
          <ul>
            {atletas.map((atleta) => (
              <li key={atleta.id}>
                <Link to={`/atletas/${atleta.id}`}>{atleta.full_name}</Link>
              </li>
            ))}
          </ul>
        )}
      </Consulta>
    </section>
  );
}
