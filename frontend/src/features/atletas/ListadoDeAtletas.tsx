import { useEffect, useState } from "react";
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
import { useRol } from "../../lib/Rol";
import { diasDesde, hace } from "./hace";

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

/**
 * Qué hacer cuando pedir como entrenador contesta 403.
 *
 * Hay dos personas distintas detrás de ese mismo código, y ofrecerles lo mismo
 * deja a una de las dos encerrada:
 *
 * - **Alguien que recién llega** y todavía no es entrenador de nadie. Para esa
 *   persona el 403 tiene salida y es darse de alta.
 * - **Un atleta** que abrió la aplicación desde otro teléfono, u otro navegador,
 *   o con el almacenamiento borrado. Su rol guardado se perdió, el que arranca
 *   por defecto es `coach`, y el 403 es la respuesta correcta a una pregunta que
 *   no debería haberse hecho. Ofrecerle «date de alta como entrenador» es
 *   mandarla a crear un espacio que no quiere.
 *
 * Se distinguen por el dato, no por una suposición: si tiene fichas como atleta,
 * es lo segundo. Ese pedido sale sólo por este camino, que es el raro.
 */
function NoEsEntrenador() {
  const fichas = useAtletas("athlete");
  const { cambiar } = useRol();
  const tiene = (fichas.data?.length ?? 0) > 0;

  useEffect(() => {
    if (tiene) cambiar("athlete");
  }, [tiene, cambiar]);

  if (fichas.isPending) return <Cargando que="tus fichas" />;
  // Mientras el cambio de rol no llegó, no se dibuja el alta de entrenador: es
  // un parpadeo que ofrece justo lo que la persona no vino a hacer.
  if (tiene) return <Cargando que="tus sesiones" />;
  return <PrimeraVez />;
}

const ESTADOS = [
  { id: "todos", titulo: "Todos" },
  { id: "activo", titulo: "Activos" },
  { id: "pausado", titulo: "Pausados" },
  { id: "archivado", titulo: "Archivados" },
] as const;

type Filtro = (typeof ESTADOS)[number]["id"];

/** Sin acentos y en minúsculas, para que buscar "martin" encuentre "Martín". */
const plano = (texto: string) =>
  texto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

/**
 * Una ficha, con lo que hace falta para decidir sin abrirla.
 *
 * El dato por el que existe esta pantalla es **hace cuánto que no entrena**. Es
 * lo que una planilla no contesta sola, y es lo que el entrenador viene a mirar:
 * quién se está cayendo. El nombre y el estado ya los sabe.
 */
function Ficha({ atleta }: { atleta: Atleta }) {
  const estado = atleta.estado ?? "activo";
  const dias = diasDesde(atleta.ultima_sesion);
  // Catorce días es la marca donde «viene flojo» pasa a ser «se fue», y no sale
  // de ningún lado más que de que dos semanas son dos microciclos. Se avisa sólo
  // en los activos: en un vínculo pausado o archivado no entrenar es lo esperado.
  const alerta = estado === "activo" && dias !== null && dias >= 14;

  return (
    <li className={`ficha ficha--${estado}`}>
      <div className="ficha__cabecera">
        <Link to={`/atletas/${atleta.id}`} className="ficha__nombre">
          {atleta.full_name}
        </Link>
        {/* Texto y no sólo color: quien no distingue los tonos tiene que poder
            leer «pausado». */}
        <span className={`chip chip--${estado}`}>{estado}</span>
      </div>

      <dl className="ficha__datos">
        <div>
          <dt>Última sesión</dt>
          <dd className={alerta ? "ficha__alerta" : undefined}>
            {hace(atleta.ultima_sesion)}
          </dd>
        </div>
        <div>
          <dt>Programa</dt>
          <dd>{atleta.programa_actual ?? "sin programa"}</dd>
        </div>
      </dl>

      {atleta.semana_actual && atleta.semanas_del_bloque ? (
        <div className="ficha__ciclo">
          <p>
            Semana{" "}
            <strong>
              {atleta.semana_actual} de {atleta.semanas_del_bloque}
            </strong>{" "}
            del bloque
          </p>
          <div
            className="progreso__barra"
            role="progressbar"
            aria-valuenow={atleta.semana_actual}
            aria-valuemin={0}
            aria-valuemax={atleta.semanas_del_bloque}
            aria-label={`Progreso del bloque de ${atleta.full_name}`}
          >
            <span
              style={{
                width: `${(atleta.semana_actual / atleta.semanas_del_bloque) * 100}%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <div className="ficha__acciones">
        <Acciones atleta={atleta} />
      </div>
    </li>
  );
}

export function ListadoDeAtletas() {
  const consulta = useAtletas();
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");

  if (consulta.isPending) return <Cargando que="los atletas" />;
  // El 403 con este motivo no es una falla: es que todavía no sos entrenador, y
  // tiene una salida. Confundirlo con "no se pudo cargar" deja a la persona
  // mirando un error que sí puede resolver.
  if (consulta.isError && consulta.error instanceof ErrorDelApi && consulta.error.status === 403) {
    return <NoEsEntrenador />;
  }
  if (consulta.isError) return <Falla que="los atletas" />;

  const texto = plano(busqueda.trim());
  const visibles = consulta.data.filter((a) => {
    const estado = a.estado ?? "activo";
    if (filtro !== "todos" && estado !== filtro) return false;
    if (!texto) return true;
    return plano(a.full_name).includes(texto) || plano(a.programa_actual ?? "").includes(texto);
  });

  return (
    <section>
      <div className="fila fila--separada">
        <h2>Atletas</h2>
        <NuevoAtleta />
      </div>

      <div className="fila filtros-de-atletas">
        <input
          type="search"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscá por nombre o programa…"
          aria-label="Buscar atletas"
        />
        <div className="fila" role="group" aria-label="Filtrar por estado">
          {ESTADOS.map((e) => (
            <button
              key={e.id}
              type="button"
              // `aria-pressed` y no una clase sola: el estado que se dibuja y el
              // que se anuncia salen del mismo atributo, así que no pueden
              // desincronizarse.
              aria-pressed={filtro === e.id}
              className={filtro === e.id ? "principal" : undefined}
              onClick={() => setFiltro(e.id)}
            >
              {e.titulo}
            </button>
          ))}
        </div>
      </div>

      {consulta.data.length === 0 ? (
        <Vacio motivo="Todavía no cargaste ningún atleta." />
      ) : visibles.length === 0 ? (
        // Distinto de no tener ninguno: acá hay atletas y el filtro los esconde.
        // Decir «todavía no cargaste ninguno» sería mentir sobre lo que pasa.
        <Vacio motivo="Ningún atleta coincide con lo que buscás." />
      ) : (
        <ul className="fichas">
          {visibles.map((atleta) => (
            <Ficha key={atleta.id} atleta={atleta} />
          ))}
        </ul>
      )}
    </section>
  );
}
