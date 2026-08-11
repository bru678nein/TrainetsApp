import { Link } from "react-router-dom";

import { useAtletas } from "../../api/consultas";

export function ListadoDeAtletas() {
  const { data, isPending, isError } = useAtletas();

  if (isPending) return <p role="status">Cargando atletas…</p>;
  if (isError) return <p role="alert">No se pudieron cargar los atletas.</p>;
  if (data.length === 0) {
    return (
      <section>
        <h2>Atletas</h2>
        <p>Todavía no cargaste ningún atleta.</p>
      </section>
    );
  }

  return (
    <section>
      <h2>Atletas</h2>
      <ul>
        {data.map((atleta) => (
          <li key={atleta.id}>
            <Link to={`/atletas/${atleta.id}`}>{atleta.full_name}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
