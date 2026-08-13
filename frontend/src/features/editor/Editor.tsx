import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorDelApi } from "../../api/cliente";
import {
  useEjercicios,
  useEscrituraDelEditor,
  useMesociclos,
  usePatrones,
  useProgramas,
  useSesion,
  type Mesociclo,
  type Programa,
  type SesionDeLaAgenda,
} from "../../api/consultas";
import { Cargando, Consulta, Falla } from "../../components/estados";
import { Mas, Tacho } from "../../components/iconos";
import { Pestanas } from "../../components/Pestanas";
import { useNombreDePatron } from "../analytics/patrones";
import { Selector } from "../../components/Selector";
import { ListaOrdenable } from "../../components/ListaOrdenable";
import { useAgenda } from "../../api/consultas";

/**
 * El editor de rutinas, en su versión mínima y fea.
 *
 * Fea a propósito: lo que hace falta verificar primero es que armar, duplicar y
 * reordenar funcionen contra la base con RLS puesto, no cómo se ve. El diseño va
 * encima de esto, no en lugar de esto.
 *
 * Lo que **no** hace, y no por falta de tiempo: no es una grilla de semanas para
 * llenar a mano. La progresión se declara una vez en el mesociclo y duplicar la
 * aplica sola, que es la forma que salió de medir cómo programa este entrenador
 * — la carga no se mueve el 60% de las veces y lo que progresa es el RIR.
 */

function mensajeDe(error: unknown): string {
  if (error instanceof ErrorDelApi) {
    return error.detalle ?? `El servidor respondió ${error.status}`;
  }
  return "No se pudo guardar";
}

function Aviso({ de }: { de: { isError: boolean; error: unknown } }) {
  if (!de.isError) return null;
  return (
    <p className="estado estado--falla" role="alert">
      {mensajeDe(de.error)}
    </p>
  );
}

// --- Mesociclos -----------------------------------------------------------------

function NuevoMesociclo({ programaId, siguiente }: { programaId: string; siguiente: number }) {
  const [label, setLabel] = useState("");
  const [semanas, setSemanas] = useState(4);
  const [progresion, setProgresion] = useState("0, 0, -1, -1");

  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/programs/${programaId}/mesocycles`, {
      ordinal: siguiente,
      label: label.trim(),
      week_count: semanas,
      rir_progression: progresion.trim()
        ? progresion.split(",").map((n) => Number(n.trim()))
        : null,
    }),
  );

  return (
    <form
      className="tarjeta tarjeta--tenue"
      onSubmit={(e) => {
        e.preventDefault();
        crear.mutate(undefined, { onSuccess: () => setLabel("") });
      }}
    >
      <h4>Nuevo mesociclo</h4>
      <label>
        Nombre <input value={label} onChange={(e) => setLabel(e.target.value)} required />
      </label>{" "}
      <Selector etiqueta="Semanas" valor={semanas} onCambio={setSemanas} max={16} />
      <label title="Cuánto se mueve el RIR en cada semana, respecto de la primera">
        Progresión de RIR{" "}
        <input value={progresion} onChange={(e) => setProgresion(e.target.value)} />
      </label>{" "}
      <button type="submit" className="principal" disabled={crear.isPending || !label.trim()}>
        Crear
      </button>
      <Aviso de={crear} />
    </form>
  );
}

function DuplicarSemana({ meso }: { meso: Mesociclo }) {
  const [desde, setDesde] = useState(1);
  const [hasta, setHasta] = useState(2);
  const duplicar = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/mesocycles/${meso.id}/duplicate-week`, { from_week: desde, to_week: hasta }),
  );

  return (
    <div className="fila">
      <strong>Duplicar semana</strong>
      <Selector etiqueta="De la" valor={desde} onCambio={setDesde} max={meso.week_count} />
      <Selector etiqueta="a la" valor={hasta} onCambio={setHasta} max={meso.week_count} />
      <button
        type="button"
        className="principal"
        onClick={() => duplicar.mutate()}
        disabled={duplicar.isPending}
      >
        {duplicar.isPending ? "Duplicando…" : "Duplicar"}
      </button>
      {meso.rir_progression ? (
        <small> — aplica la progresión [{meso.rir_progression.join(", ")}]</small>
      ) : (
        <small> — este bloque no declara progresión: copia plano</small>
      )}
      <Aviso de={duplicar} />
    </div>
  );
}

// --- Una sesión y su contenido --------------------------------------------------

function NuevaSerie({ prescripcionId }: { prescripcionId: string }) {
  const [reps, setReps] = useState("8");
  const [rir, setRir] = useState("2");
  const [carga, setCarga] = useState("");

  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/prescriptions/${prescripcionId}/sets`, {
      reps_min: reps ? Number(reps) : null,
      reps_max: reps ? Number(reps) : null,
      rir_min: rir ? Number(rir) : null,
      rir_max: rir ? Number(rir) : null,
      // Sin carga es autorregulada: el peso lo elige el atleta ese día. No se
      // manda cero, que sería una barra vacía y cuenta como carga en el tonelaje.
      target_load_kg: carga ? Number(carga) : null,
    }),
  );

  return (
    <form
      className="fila"
      onSubmit={(e) => {
        e.preventDefault();
        crear.mutate();
      }}
    >
      <input
        size={3}
        value={reps}
        onChange={(e) => setReps(e.target.value)}
        aria-label="Repeticiones"
        placeholder="reps"
      />{" "}
      <input
        size={3}
        value={rir}
        onChange={(e) => setRir(e.target.value)}
        aria-label="RIR"
        placeholder="RIR"
      />{" "}
      <input
        size={4}
        value={carga}
        onChange={(e) => setCarga(e.target.value)}
        aria-label="Carga en kg"
        placeholder="kg"
      />{" "}
      <button type="submit" disabled={crear.isPending}>
        + serie
      </button>
      <Aviso de={crear} />
    </form>
  );
}

function ContenidoDeSesion({ sesionId }: { sesionId: string }) {
  const detalle = useSesion(sesionId, "coach");
  const ejercicios = useEjercicios();
  const [elegido, setElegido] = useState("");

  const agregar = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/sessions/${sesionId}/prescriptions`, { exercise_id: elegido }),
  );
  const borrarSerie = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/prescribed-sets/${id}`),
  );
  const borrarEjercicio = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/prescriptions/${id}`),
  );
  const duplicarEjercicio = useEscrituraDelEditor<unknown, string>((enviar, _, id) =>
    enviar(`/api/prescriptions/${id}/duplicate`),
  );
  const reordenar = useEscrituraDelEditor<unknown, string[]>((_, mutar, ids) =>
    mutar("PUT", `/api/sessions/${sesionId}/prescriptions/order`, { ids }),
  );

  return (
    <div>
      <Consulta consulta={detalle} que="la sesión">
        {(datos) => (
          <>
            {datos.blocks.length === 0 ? (
              <p>Sin ejercicios todavía.</p>
            ) : (
              <ListaOrdenable
                elementos={datos.blocks.map((b) => ({ ...b, id: b.prescription_id }))}
                onOrdenar={(ids) => reordenar.mutate(ids)}
                deshabilitado={reordenar.isPending}
              >
                {(bloque) => (
                  <>
                    <strong>{bloque.exercise}</strong>{" "}
                    <button
                      type="button"
                      className="sutil"
                      onClick={() => duplicarEjercicio.mutate(bloque.prescription_id)}
                    >
                      duplicar
                    </button>{" "}
                    <button
                      type="button"
                      className="peligro"
                      onClick={() => borrarEjercicio.mutate(bloque.prescription_id)}
                    >
                      borrar
                    </button>
                    <ul className="lista">
                      {bloque.sets.map((serie) => (
                        <li key={serie.id}>
                          {serie.reps_min ?? "?"}
                          {serie.reps_max && serie.reps_max !== serie.reps_min
                            ? `-${serie.reps_max}`
                            : ""}{" "}
                          reps · RIR {serie.rir_min ?? "?"} ·{" "}
                          {serie.target_load_kg != null
                            ? `${serie.target_load_kg} kg`
                            : "autorregulada"}{" "}
                          <button
                            type="button"
                            className="sutil"
                            onClick={() => borrarSerie.mutate(serie.id)}
                            aria-label={`Borrar la serie ${serie.set_number}`}
                          >
                            ×
                          </button>
                        </li>
                      ))}
                    </ul>
                    <NuevaSerie prescripcionId={bloque.prescription_id} />
                  </>
                )}
              </ListaOrdenable>
            )}
          </>
        )}
      </Consulta>

      <Consulta consulta={ejercicios} que="el catálogo">
        {(lista) => (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (elegido) agregar.mutate();
            }}
          >
            <select value={elegido} onChange={(e) => setElegido(e.target.value)}>
              <option value="">— elegí un ejercicio —</option>
              {lista.map((ej) => (
                <option key={ej.id} value={ej.id}>
                  {ej.name}
                </option>
              ))}
            </select>{" "}
            <button type="submit" disabled={!elegido || agregar.isPending}>
              Agregar ejercicio
            </button>
            <Aviso de={agregar} />
          </form>
        )}
      </Consulta>
      <Aviso de={borrarSerie} />
      <Aviso de={borrarEjercicio} />
      <Aviso de={reordenar} />
    </div>
  );
}

// --- El catálogo ----------------------------------------------------------------

function Catalogo() {
  const patrones = usePatrones();
  const ejercicios = useEjercicios();
  const [nombre, setNombre] = useState("");
  const [patron, setPatron] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar("/api/exercises", { name: nombre.trim(), pattern_code: patron }),
  );

  const nombreDe = useNombreDePatron();

  return (
    <>
      <section className="tarjeta">
        <h3>Crear un ejercicio</h3>
        <Consulta consulta={patrones} que="los patrones">
          {(lista) => (
            <form
              className="fila"
              onSubmit={(e) => {
                e.preventDefault();
                crear.mutate(undefined, { onSuccess: () => setNombre("") });
              }}
            >
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Nombre"
                aria-label="Nombre del ejercicio"
                required
              />
              <select
                value={patron}
                onChange={(e) => setPatron(e.target.value)}
                aria-label="Patrón de movimiento"
                required
              >
                <option value="">— patrón de movimiento —</option>
                {lista.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.label_es}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="principal"
                disabled={!nombre.trim() || !patron || crear.isPending}
              >
                Crear
              </button>
            </form>
          )}
        </Consulta>
        <small>El patrón es obligatorio: sin él no hay análisis de volumen.</small>
        <Aviso de={crear} />
      </section>

      <section className="tarjeta">
        <h3>El catálogo</h3>
        <Consulta
          consulta={ejercicios}
          que="el catálogo"
          vacio={{
            cuando: (lista) => lista.length === 0,
            motivo: "No hay ejercicios todavía. Creá el primero acá arriba.",
          }}
        >
          {(lista) => (
            <ul className="lista">
              {lista.map((ej) => (
                <li key={ej.id}>
                  {ej.name}
                  <span className="chip">{nombreDe(ej.pattern_code)}</span>
                  {ej.coach_id === null ? <small className="empuja">global</small> : null}
                </li>
              ))}
            </ul>
          )}
        </Consulta>
      </section>
    </>
  );
}

// --- La pantalla ----------------------------------------------------------------

function NuevoPrograma({ atletaId }: { atletaId: string }) {
  const [nombre, setNombre] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/athletes/${atletaId}/programs`, { name: nombre.trim() }),
  );
  return (
    <form
      className="fila"
      onSubmit={(e) => {
        e.preventDefault();
        crear.mutate(undefined, { onSuccess: () => setNombre("") });
      }}
    >
      <input
        value={nombre}
        onChange={(e) => setNombre(e.target.value)}
        placeholder="Nombre del programa"
        required
      />{" "}
      <button type="submit" className="principal" disabled={!nombre.trim() || crear.isPending}>
        Crear programa
      </button>
      <Aviso de={crear} />
    </form>
  );
}

/**
 * Las semanas del bloque, una al lado de la otra.
 *
 * En rejilla y no en una lista corrida, y no es decoración: un mesociclo es un
 * bloque de semanas comparables entre sí — la 3 se entiende mirando la 2. En
 * lista, la 4 queda a un scroll de la 1 y esa comparación deja de existir.
 *
 * **Se dibujan todas las semanas, incluidas las vacías.** Es lo que hace visible
 * que la 3 no está armada todavía, que en una lista de lo que hay no se ve: lo
 * que falta no ocupa lugar.
 */
function Semana({
  meso,
  numero,
  sesiones,
  abierta,
  onAbrir,
}: {
  meso: Mesociclo;
  numero: number;
  sesiones: SesionDeLaAgenda[];
  abierta: string | null;
  onAbrir: (id: string | null) => void;
}) {
  const usados = new Set(sesiones.map((s) => s.day_number));
  const siguiente = [1, 2, 3, 4, 5, 6, 7].find((d) => !usados.has(d));

  const agregar = useEscrituraDelEditor<unknown, number>((enviar, _, dia) =>
    enviar(`/api/mesocycles/${meso.id}/sessions`, { week_number: numero, day_number: dia }),
  );
  const borrar = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/sessions/${id}`),
  );

  return (
    <section className="semana">
      <h4 className="semana__titulo">Semana {numero}</h4>
      {sesiones.length === 0 ? (
        <p className="semana__vacia">Sin sesiones</p>
      ) : (
        <ul className="semana__sesiones">
          {sesiones.map((s) => {
            const abiertaEsta = abierta === s.id;
            return (
              <li key={s.id} className="dia">
                <div className="dia__cabecera">
                  <button
                    type="button"
                    className="revelar"
                    aria-expanded={abiertaEsta}
                    onClick={() => onAbrir(abiertaEsta ? null : s.id)}
                  >
                    {/* La flecha gira con el estado y no cambia de carácter: así
                        el movimiento cuenta qué pasó, en vez de aparecer un
                        signo nuevo donde había otro. */}
                    <span className="revelar__flecha" aria-hidden="true">
                      ▸
                    </span>
                    Día {s.day_number}
                  </button>
                  <button
                    type="button"
                    className="dia__borrar"
                    onClick={() => {
                      if (abiertaEsta) onAbrir(null);
                      borrar.mutate(s.id);
                    }}
                    disabled={borrar.isPending}
                    aria-label={`Borrar el día ${s.day_number} de la semana ${numero}`}
                    title="Borrar este día"
                  >
                    <Tacho />
                  </button>
                </div>
                {abiertaEsta ? <ContenidoDeSesion sesionId={s.id} /> : null}
              </li>
            );
          })}
        </ul>
      )}

      {/* Al fondo del panel y después de todos los días, que es donde va lo que
          se agrega: la lista se lee de arriba abajo y el botón es su final. */}
      <button
        type="button"
        className="semana__agregar"
        onClick={() => siguiente && agregar.mutate(siguiente)}
        disabled={!siguiente || agregar.isPending}
        title={siguiente ? `Agregar el día ${siguiente}` : "Esta semana ya tiene los siete días"}
      >
        <Mas /> {siguiente ? `Día ${siguiente}` : "Semana completa"}
      </button>
      <Aviso de={agregar} />
      <Aviso de={borrar} />
    </section>
  );
}

function Bloque({ meso, atletaId }: { meso: Mesociclo; atletaId: string }) {
  const agenda = useAgenda(atletaId, "coach");
  const [abierta, setAbierta] = useState<string | null>(null);
  const semanas = Array.from({ length: meso.week_count }, (_, i) => i + 1);

  return (
    <section className="tarjeta">
      <h3>
        {meso.ordinal}. {meso.label} — {meso.week_count} semanas
      </h3>
      <DuplicarSemana meso={meso} />
      <Consulta consulta={agenda} que="las sesiones">
        {(todas) => {
          const mias = todas.filter((s) => s.mesocycle === meso.label);
          return (
            <div className="semanas">
              {semanas.map((numero) => (
                <Semana
                  key={numero}
                  meso={meso}
                  numero={numero}
                  sesiones={mias
                    .filter((s) => s.week_number === numero)
                    .sort((a, b) => a.day_number - b.day_number)}
                  abierta={abierta}
                  onAbrir={setAbierta}
                />
              ))}
            </div>
          );
        }}
      </Consulta>
    </section>
  );
}

export function Editor() {
  const { atletaId } = useParams();
  const programas = useProgramas(atletaId ?? "");
  const [programa, setPrograma] = useState<string | undefined>();
  const mesociclos = useMesociclos(programa);

  if (!atletaId) return null;
  if (programas.isPending) return <Cargando que="los programas" />;
  if (programas.isError) return <Falla que="los programas" />;

  const elegido: Programa | undefined =
    programas.data.find((p) => p.id === programa) ?? programas.data[0];
  if (elegido && elegido.id !== programa) setPrograma(elegido.id);

  const bloques = (
    <>
      <NuevoPrograma atletaId={atletaId} />
      {programas.data.length > 1 ? (
        <label>
          Programa{" "}
          <select value={programa ?? ""} onChange={(e) => setPrograma(e.target.value)}>
            {programas.data.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {elegido ? (
        <>
          <h3>{elegido.name}</h3>
          <NuevoMesociclo programaId={elegido.id} siguiente={(mesociclos.data?.length ?? 0) + 1} />
          <Consulta
            consulta={mesociclos}
            que="los mesociclos"
            vacio={{
              cuando: (lista) => lista.length === 0,
              motivo: "Este programa no tiene bloques todavía. Creá el primero acá arriba.",
            }}
          >
            {(lista) =>
              lista.map((meso) => <Bloque key={meso.id} meso={meso} atletaId={atletaId} />)
            }
          </Consulta>
        </>
      ) : (
        <p>Este atleta no tiene programas. Creá el primero.</p>
      )}
    </>
  );

  return (
    <>
      <p>
        <Link to={`/atletas/${atletaId}`}>← Panel del atleta</Link>
      </p>
      <h2>Editor de rutinas</h2>
      {/* Dos cosas distintas que estaban una encima de la otra: armar el bloque
          de este atleta, y mantener el catálogo, que es del entrenador y lo
          comparten todos sus atletas. Verlas juntas hacía parecer que crear un
          ejercicio era parte de armar este programa. */}
      <Pestanas
        pestanas={[
          { id: "mesociclos", titulo: "Mesociclos", contenido: bloques },
          { id: "ejercicios", titulo: "Ejercicios", contenido: <Catalogo /> },
        ]}
      />
    </>
  );
}
