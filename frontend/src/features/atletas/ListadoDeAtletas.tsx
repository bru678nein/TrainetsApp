import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorDelApi } from "../../api/cliente";
import {
  useAtletas,
  useCambiarEstado,
  useCrearAtleta,
  useCrearCoach,
  type Accion,
  type Atleta,
} from "../../api/consultas";
import { Cargando, Falla, Vacio } from "../../components/estados";

/**
 * Quien entra por primera vez no tiene perfil de entrenador, y hasta ahora eso
 * era un 403 y punto muerto.
 *
 * Se ofrece acá y no en una ruta propia porque es donde se descubre: el listado
 * es la primera pantalla, y el error que devuelve dice exactamente qué falta.
 */
function PrimeraVez() {
  const alta = useCrearCoach();
  return (
    <section className="tarjeta">
      <h2>Todavía no tenés un espacio de entrenador</h2>
      <p>Creá el tuyo y empezá a cargar atletas.</p>
      <button type="button" className="principal" onClick={() => alta.mutate()} disabled={alta.isPending}>
        {alta.isPending ? "Creando…" : "Crear mi espacio"}
      </button>
      {alta.isError ? (
        <p className="estado estado--falla" role="alert">
          No se pudo crear el espacio.
        </p>
      ) : null}
    </section>
  );
}

function NuevoAtleta() {
  const [nombre, setNombre] = useState("");
  const crear = useCrearAtleta();

  return (
    <form
      className="fila"
      onSubmit={(e) => {
        e.preventDefault();
        if (!nombre.trim()) return;
        crear.mutate({ full_name: nombre.trim() }, { onSuccess: () => setNombre("") });
      }}
    >
      <label>
        Nombre del atleta{" "}
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} required />
      </label>
      <button type="submit" className="principal" disabled={crear.isPending || !nombre.trim()}>
        {crear.isPending ? "Creando…" : "Agregar"}
      </button>
      {crear.isError ? (
        <p className="estado estado--falla" role="alert">
          No se pudo crear la ficha.
        </p>
      ) : null}
    </form>
  );
}

/** Las acciones que el estado admite. La tabla completa vive en el backend; acá
 *  se ofrece lo que tiene sentido y el servidor rechaza el resto con su motivo. */
const ACCIONES: Record<string, Accion[]> = {
  activo: ["pausar", "archivar"],
  pausado: ["reanudar", "archivar"],
  archivado: ["reactivar"],
};

function Acciones({ atleta }: { atleta: Atleta }) {
  const cambiar = useCambiarEstado(atleta.id);
  const estado = atleta.estado ?? "activo";

  return (
    <>
      {(ACCIONES[estado] ?? []).map((accion) => (
        <button
          key={accion}
          type="button"
          className={accion === "archivar" ? "peligro" : "sutil"}
          onClick={() => cambiar.mutate(accion)}
          disabled={cambiar.isPending}
        >
          {accion}
        </button>
      ))}
      {cambiar.isError ? (
        <span className="estado estado--falla" role="alert">
          {cambiar.error instanceof ErrorDelApi && cambiar.error.detalle
            ? cambiar.error.detalle
            : "no se pudo"}
        </span>
      ) : null}
    </>
  );
}

export function ListadoDeAtletas() {
  const consulta = useAtletas();

  if (consulta.isPending) return <Cargando que="los atletas" />;
  // El 403 con este motivo no es una falla: es que todavía no sos entrenador, y
  // tiene una salida. Confundirlo con "no se pudo cargar" deja a la persona
  // mirando un error que sí puede resolver.
  if (
    consulta.isError &&
    consulta.error instanceof ErrorDelApi &&
    consulta.error.status === 403
  ) {
    return <PrimeraVez />;
  }
  if (consulta.isError) return <Falla que="los atletas" />;

  return (
    <section className="tarjeta">
      <h2>Atletas</h2>
      <NuevoAtleta />
      {consulta.data.length === 0 ? (
        <Vacio motivo="Todavía no cargaste ningún atleta." />
      ) : (
        <ul className="lista">
          {consulta.data.map((atleta) => {
            const estado = atleta.estado ?? "activo";
            return (
              <li key={atleta.id}>
                <Link to={`/atletas/${atleta.id}`}>{atleta.full_name}</Link>
                {/* Texto y no sólo color: quien no distingue los tonos tiene que
                    poder leer «pausado». */}
                <span className={`chip chip--${estado}`}>{estado}</span>
                <span className="empuja" />
                <Acciones atleta={atleta} />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
