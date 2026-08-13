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
} from "../../api/consultas";
import { Cargando, Consulta, Falla } from "../../components/estados";
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
      <label>
        Semanas{" "}
        <input
          type="number"
          min={1}
          max={16}
          value={semanas}
          onChange={(e) => setSemanas(Number(e.target.value))}
        />
      </label>{" "}
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

  const semanas = Array.from({ length: meso.week_count }, (_, i) => i + 1);
  return (
    <div className="fila">
      <strong>Duplicar semana</strong>{" "}
      <select value={desde} onChange={(e) => setDesde(Number(e.target.value))}>
        {semanas.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>{" "}
      sobre{" "}
      <select value={hasta} onChange={(e) => setHasta(Number(e.target.value))}>
        {semanas.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>{" "}
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

function NuevaSesion({ meso }: { meso: Mesociclo }) {
  const [semana, setSemana] = useState(1);
  const [dia, setDia] = useState(1);
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar(`/api/mesocycles/${meso.id}/sessions`, { week_number: semana, day_number: dia }),
  );
  return (
    <form
      className="fila"
      onSubmit={(e) => {
        e.preventDefault();
        crear.mutate();
      }}
    >
      <label>
        Semana{" "}
        <input
          type="number"
          min={1}
          max={meso.week_count}
          value={semana}
          onChange={(e) => setSemana(Number(e.target.value))}
        />
      </label>{" "}
      <label>
        Día{" "}
        <input
          type="number"
          min={1}
          max={7}
          value={dia}
          onChange={(e) => setDia(Number(e.target.value))}
        />
      </label>{" "}
      <button type="submit" disabled={crear.isPending}>
        Agregar sesión
      </button>
      <Aviso de={crear} />
    </form>
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

function NuevoEjercicio() {
  const patrones = usePatrones();
  const [nombre, setNombre] = useState("");
  const [patron, setPatron] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar("/api/exercises", { name: nombre.trim(), pattern_code: patron }),
  );

  return (
    <details className="tarjeta tarjeta--tenue">
      <summary>Crear un ejercicio</summary>
      <Consulta consulta={patrones} que="los patrones">
        {(lista) => (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              crear.mutate(undefined, { onSuccess: () => setNombre("") });
            }}
          >
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Nombre"
              required
            />{" "}
            <select value={patron} onChange={(e) => setPatron(e.target.value)} required>
              <option value="">— patrón de movimiento —</option>
              {lista.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.label_es}
                </option>
              ))}
            </select>{" "}
            <button type="submit" disabled={!nombre.trim() || !patron || crear.isPending}>
              Crear
            </button>
            <small> — el patrón es obligatorio: sin él no hay análisis de volumen.</small>
            <Aviso de={crear} />
          </form>
        )}
      </Consulta>
    </details>
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

function Bloque({ meso, atletaId }: { meso: Mesociclo; atletaId: string }) {
  const agenda = useAgenda(atletaId, "coach");
  const [abierta, setAbierta] = useState<string | null>(null);

  return (
    <section className="tarjeta">
      <h3>
        {meso.ordinal}. {meso.label} — {meso.week_count} semanas
      </h3>
      <DuplicarSemana meso={meso} />
      <NuevaSesion meso={meso} />
      <Consulta consulta={agenda} que="las sesiones">
        {(todas) => {
          const mias = todas.filter((s) => s.mesocycle === meso.label);
          if (mias.length === 0) return <p>Sin sesiones todavía.</p>;
          return (
            <ul>
              {mias
                .slice()
                .sort((a, b) => a.week_number - b.week_number || a.day_number - b.day_number)
                .map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      className="sutil"
                      aria-expanded={abierta === s.id}
                      onClick={() => setAbierta(abierta === s.id ? null : s.id)}
                    >
                      Semana {s.week_number}, día {s.day_number}
                    </button>
                    {abierta === s.id ? <ContenidoDeSesion sesionId={s.id} /> : null}
                  </li>
                ))}
            </ul>
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

  return (
    <>
      <p>
        <Link to={`/atletas/${atletaId}`}>← Panel del atleta</Link>
      </p>
      <h2>Editor de rutinas</h2>
      <NuevoPrograma atletaId={atletaId} />
      <NuevoEjercicio />

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
          <NuevoMesociclo
            programaId={elegido.id}
            siguiente={(mesociclos.data?.length ?? 0) + 1}
          />
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
}
