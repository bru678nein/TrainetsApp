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
      <button
        type="button"
        className="principal"
        onClick={() => alta.mutate()}
        disabled={alta.isPending}
      >
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
        crear.mutate(
          { full_name: nombre.trim() },
          { onSuccess: () => setNombre("") },
        );
      }}
    >
      <label>
        Nombre del atleta{" "}
        <input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          required
        />
      </label>
      <button
        type="submit"
        className="principal"
        disabled={crear.isPending || !nombre.trim()}
      >
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
 * Qué tan urgente es esta ficha. Más chico, más arriba.
 *
 * El listado no se ordena alfabéticamente y eso es la decisión de la pantalla:
 * la pregunta del domingo a la noche no es «¿dónde está Ana?» —para eso está el
 * buscador— sino «¿a quién le tengo que dar bola?».
 *
 * El orden es: sin programa, después los que se están cayendo de más a menos,
 * después el resto, y al final los que no están entrenando por decisión del
 * entrenador. Un vínculo pausado o archivado no aparece arriba por no registrar:
 * no registrar es exactamente lo que se espera de él.
 */
function urgencia(atleta: Atleta): [number, number] {
  const estado = atleta.estado ?? "activo";
  if (estado === "archivado") return [4, 0];
  if (estado === "pausado") return [3, 0];
  if (!atleta.programa_actual) return [0, 0];
  const dias = diasDesde(atleta.ultima_sesion);
  // Nunca registró y todavía no tiene cuenta: no se cayó, no empezó. Va con los
  // que están al día en vez de encabezar la lista con una alarma falsa.
  if (dias === null) return atleta.tiene_cuenta ? [1, 9999] : [2, 0];
  return [dias >= DIAS_DE_CAIDA ? 1 : 2, -dias];
}

/** Dos semanas son dos microciclos: la marca donde «viene flojo» pasa a «se fue». */
const DIAS_DE_CAIDA = 14;

/**
 * Una fila, con lo que hace falta para decidir sin abrirla.
 *
 * Fila y no tarjeta, y es densidad elegida a propósito: un entrenador con veinte
 * atletas quiere verlos todos sin scrollear. Lo que no se comprimió son los
 * objetivos táctiles — los botones siguen en 44px. La densidad se paga en
 * tipografía y en aire, nunca en el tamaño de lo que hay que apretar.
 */
function FilaDeAtleta({ atleta }: { atleta: Atleta }) {
  const estado = atleta.estado ?? "activo";
  const dias = diasDesde(atleta.ultima_sesion);
  const cayendose =
    estado === "activo" && dias !== null && dias >= DIAS_DE_CAIDA;
  const sinPrograma = estado === "activo" && !atleta.programa_actual;

  return (
    <li className={`atleta atleta--${estado}`}>
      <div className="atleta__quien">
        <Link to={`/atletas/${atleta.id}`} className="atleta__nombre">
          {atleta.full_name}
        </Link>
        {/* No es un problema a resolver: es el orden en que el producto
            funciona. Por eso lo dice sin color de alerta. */}
        {atleta.tiene_cuenta === false ? (
          <span className="chip">Sin cuenta todavía</span>
        ) : null}
      </div>

      {/* Texto y no sólo color: quien no distingue los tonos tiene que poder
          leer «pausado». */}
      <span className={`chip chip--${estado}`}>
        <i className="chip__punto" aria-hidden="true" />
        {estado}
      </span>

      <span className={cayendose ? "atleta__caida" : "atleta__dato"}>
        {hace(atleta.ultima_sesion)}
      </span>

      <span className="atleta__dato">
        {sinPrograma ? (
          <strong className="atleta__sin-programa">Sin programa</strong>
        ) : (
          <>
            {atleta.programa_actual ?? "—"}
            {atleta.semana_actual && atleta.semanas_del_bloque ? (
              <>
                {" · "}
                <span className="numeros">
                  semana {atleta.semana_actual} de {atleta.semanas_del_bloque}
                </span>
              </>
            ) : null}
          </>
        )}
      </span>

      <span className="atleta__acciones">
        {/* El camino obvio primero, y distinto según lo que falte. Cambiar de
            estado es lo raro y queda detrás, no al revés. */}
        {estado === "activo" ? (
          <Link
            to={`/atletas/${atleta.id}`}
            className={sinPrograma ? "boton boton--llama" : "boton"}
          >
            {sinPrograma ? "Armar el primer bloque" : "Armar la semana"}
          </Link>
        ) : null}
        <Acciones atleta={atleta} />
      </span>
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
  if (
    consulta.isError &&
    consulta.error instanceof ErrorDelApi &&
    consulta.error.status === 403
  ) {
    return <NoEsEntrenador />;
  }
  if (consulta.isError) return <Falla que="los atletas" />;

  // Cuántas piden atención se cuenta sobre **todas** y no sobre las visibles: el
  // número del encabezado tiene que seguir siendo cierto con un filtro puesto,
  // que es justo cuando alguien podría creer que ya no queda nada por mirar.
  const piden = consulta.data.filter((a) => urgencia(a)[0] <= 1).length;

  const texto = plano(busqueda.trim());
  const visibles = consulta.data.filter((a) => {
    const estado = a.estado ?? "activo";
    if (filtro !== "todos" && estado !== filtro) return false;
    if (!texto) return true;
    return (
      plano(a.full_name).includes(texto) ||
      plano(a.programa_actual ?? "").includes(texto)
    );
  });
  const ordenadas = [...visibles].sort((a, b) => {
    const [ga, da] = urgencia(a);
    const [gb, dbb] = urgencia(b);
    return ga - gb || da - dbb || a.full_name.localeCompare(b.full_name, "es");
  });

  return (
    <section>
      <div className="fila fila--separada">
        <div>
          <h2>Atletas</h2>
          <p className="atletas__resumen">
            <span className="numeros">{consulta.data.length}</span> fichas
            {piden > 0 ? (
              <>
                {" · "}
                <strong className="atleta__caida">
                  <span className="numeros">{piden}</span>{" "}
                  {piden === 1 ? "pide atención" : "piden atención"}
                </strong>
              </>
            ) : null}
          </p>
        </div>
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
        // El primer vacío es el único lugar donde el producto puede explicar su
        // orden —ficha, programa, y el link recién al final— sin que nadie tenga
        // que leer un manual.
        <Vacio motivo="Todavía no tenés atletas. Creá la ficha primero y armale el programa entero: el link se lo mandás cuando esté listo, no necesita cuenta para que empieces." />
      ) : ordenadas.length === 0 ? (
        // Distinto de no tener ninguno: acá hay atletas y el filtro los esconde.
        // Decir «todavía no cargaste ninguno» sería mentir sobre lo que pasa.
        <Vacio motivo="Ningún atleta coincide con lo que buscás." />
      ) : (
        <ul className="atletas">
          <li className="atleta atleta--encabezado" aria-hidden="true">
            <span>Atleta</span>
            <span>Estado</span>
            <span>Último registro</span>
            <span>Bloque</span>
            <span />
          </li>
          {ordenadas.map((atleta) => (
            <FilaDeAtleta key={atleta.id} atleta={atleta} />
          ))}
        </ul>
      )}
    </section>
  );
}
