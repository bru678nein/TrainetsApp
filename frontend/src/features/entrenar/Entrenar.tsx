import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useAgenda,
  useAtletas,
  useRegistrarSerie,
  useSesion,
  type SerieDelDia,
} from "../../api/consultas";
import { Consulta } from "../../components/estados";

/**
 * Lo que el atleta ve y usa, parado en el gimnasio entre serie y serie.
 *
 * De acá sale la única restricción de diseño que esta versión sí respeta aunque
 * sea fea: **el gesto normal es confirmar, no escribir**. Los campos vienen
 * cargados con lo que le prescribieron, así que registrar una serie que salió
 * como estaba planificada es un botón. Un formulario en blanco con tres números
 * a tipear, con una mano y treinta segundos de descanso, no se usa — y si no se
 * usa, no hay datos y el resto del producto no existe.
 *
 * Pide siempre con rol `athlete` y no con el del interruptor: registrar es del
 * atleta, la policy rechaza al entrenador, y dejar que un `select` de otra
 * pantalla cambie eso sería ofrecer un botón que contesta 409.
 */

function Serie({ serie, sesionId }: { serie: SerieDelDia; sesionId: string }) {
  const registrar = useRegistrarSerie(sesionId);
  const hecha = serie.reps_done != null;

  // Lo prescrito como valor inicial. Si ya se registró, lo registrado, para que
  // corregir sea editar lo que hay y no volver a escribirlo entero.
  const [reps, setReps] = useState(String(serie.reps_done ?? serie.reps_min ?? ""));
  const [carga, setCarga] = useState(String(serie.load_done_kg ?? serie.target_load_kg ?? ""));
  const [rir, setRir] = useState(String(serie.rir_done ?? serie.rir_min ?? ""));

  const mandar = (extra: { was_skipped?: boolean } = {}) =>
    registrar.mutate({
      serieId: serie.id,
      reps: reps === "" ? null : Number(reps),
      load_kg: carga === "" ? null : Number(carga),
      rir: rir === "" ? null : Number(rir),
      ...extra,
    });

  return (
    <li>
      <span>
        Serie {serie.set_number} · pedían {serie.reps_min ?? "?"}
        {serie.reps_max && serie.reps_max !== serie.reps_min ? `-${serie.reps_max}` : ""} reps, RIR{" "}
        {serie.rir_min ?? "?"}
        {serie.target_load_kg != null ? `, ${serie.target_load_kg} kg` : ", peso a elección"}
      </span>
      <div>
        <input
          size={3}
          inputMode="numeric"
          value={reps}
          onChange={(e) => setReps(e.target.value)}
          aria-label={`Repeticiones de la serie ${serie.set_number}`}
        />{" "}
        <input
          size={4}
          inputMode="decimal"
          value={carga}
          onChange={(e) => setCarga(e.target.value)}
          aria-label={`Carga de la serie ${serie.set_number}`}
        />{" "}
        kg{" "}
        <input
          size={3}
          inputMode="decimal"
          value={rir}
          onChange={(e) => setRir(e.target.value)}
          aria-label={`RIR de la serie ${serie.set_number}`}
        />{" "}
        RIR{" "}
        <button type="button" onClick={() => mandar()} disabled={registrar.isPending}>
          {registrar.isPending ? "…" : hecha ? "Corregir" : "Listo"}
        </button>{" "}
        <button
          type="button"
          onClick={() => mandar({ was_skipped: true })}
          disabled={registrar.isPending}
        >
          La salté
        </button>
        {hecha ? <strong> ✓</strong> : null}
      </div>
      {registrar.isError ? (
        <p className="estado estado--falla" role="alert">
          No se pudo registrar.
        </p>
      ) : null}
    </li>
  );
}

export function SesionDelDia() {
  const { sesionId } = useParams();
  const detalle = useSesion(sesionId ?? "", "athlete");
  if (!sesionId) return null;

  return (
    <>
      <p>
        <Link to="/entrenar">← Mis sesiones</Link>
      </p>
      <Consulta consulta={detalle} que="la sesión">
        {(datos) => (
          <>
            <h2>
              {datos.mesocycle} · semana {datos.week_number}, día {datos.day_number}
            </h2>
            {datos.blocks.map((bloque) => (
              <section key={bloque.prescription_id}>
                <h3>{bloque.exercise}</h3>
                {bloque.coach_note ? <p>{bloque.coach_note}</p> : null}
                {bloque.rest_seconds ? <p>Descanso: {bloque.rest_seconds}s</p> : null}
                <ul>
                  {bloque.sets.map((serie) => (
                    <Serie key={serie.id} serie={serie} sesionId={sesionId} />
                  ))}
                </ul>
              </section>
            ))}
          </>
        )}
      </Consulta>
    </>
  );
}

/**
 * Las sesiones del atleta.
 *
 * Pasa por el listado de fichas porque una persona puede ser atleta de varios
 * entrenadores, y en ese caso tiene más de una agenda. Con una sola ficha el
 * paso es invisible: se entra directo.
 */
export function MisSesiones() {
  const fichas = useAtletas("athlete");
  return (
    <Consulta
      consulta={fichas}
      que="tus fichas"
      vacio={{
        cuando: (lista) => lista.length === 0,
        motivo: "Todavía no reclamaste ninguna ficha. Pedile el link a tu entrenador.",
      }}
    >
      {(lista) =>
        lista.map((ficha) => <AgendaDeUnaFicha key={ficha.id} atletaId={ficha.id} />)
      }
    </Consulta>
  );
}

function AgendaDeUnaFicha({ atletaId }: { atletaId: string }) {
  const agenda = useAgenda(atletaId, "athlete");
  return (
    <section>
      <h2>Mis sesiones</h2>
      <Consulta
        consulta={agenda}
        que="tus sesiones"
        vacio={{
          cuando: (lista) => lista.length === 0,
          motivo: "Tu entrenador todavía no cargó sesiones.",
        }}
      >
        {(lista) => (
          <ul>
            {lista.map((s) => (
              <li key={s.id}>
                <Link to={`/entrenar/${s.id}`}>
                  {s.mesocycle} · semana {s.week_number}, día {s.day_number}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Consulta>
    </section>
  );
}
