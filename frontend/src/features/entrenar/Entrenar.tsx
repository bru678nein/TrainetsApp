import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useAgenda,
  useAtletas,
  useRegistrarSerie,
  useSesion,
  type BloqueDelDia,
  type SerieDelDia,
} from "../../api/consultas";
import { Consulta } from "../../components/estados";

/**
 * Lo que el atleta ve y usa, parado en el gimnasio entre serie y serie.
 *
 * De acá sale la única restricción de diseño que manda sobre esta pantalla:
 * **el gesto normal es confirmar, no escribir**. Medido sobre la programación
 * real, 473 de 473 ejercicios prescriptos tienen todas sus series idénticas, y
 * la carga se repite el 60% de las veces. O sea que casi siempre la persona hizo
 * exactamente lo que le pidieron, y la pantalla tiene que cobrar eso barato.
 *
 * La versión anterior mostraba **las 21 series de un día abiertas a la vez**:
 * 5.417px de alto, 6,7 pantallas de scroll y 105 controles, entre los que había
 * que buscar cuál era la que seguía. Medido a 375px sobre un día real de siete
 * ejercicios. Funcionaba y era un formulario de carga, no algo que se usa con
 * una mano y treinta segundos de descanso.
 *
 * Ahora: lo hecho se colapsa a un renglón, lo que viene se insinúa, y **abierta
 * queda una sola serie** — la próxima. Los números se empujan con `−` y `+` en
 * vez de tipearse, porque el gesto real no es escribir «82», es «uno más que la
 * vez pasada».
 *
 * Pide siempre con rol `athlete` y no con el del interruptor: registrar es del
 * atleta, la policy rechaza al entrenador, y dejar que un `select` de otra
 * pantalla cambie eso sería ofrecer un botón que contesta 409.
 */

const hecha = (s: SerieDelDia) => s.reps_done != null;

/** «3x8 @ 60kg», o «3x8 · peso a elección» cuando no hay carga prescrita. */
function objetivoDe(bloque: BloqueDelDia): string {
  const primera = bloque.sets[0];
  if (!primera) return "sin series";
  const reps =
    primera.reps_max && primera.reps_max !== primera.reps_min
      ? `${primera.reps_min}-${primera.reps_max}`
      : `${primera.reps_min ?? "?"}`;
  const carga =
    primera.target_load_kg != null
      ? `@ ${primera.target_load_kg} kg`
      : "· peso a elección";
  return `${bloque.sets.length}×${reps} ${carga}`;
}

/**
 * Un número que se empuja, no que se escribe.
 *
 * El `input` sigue estando y acepta teclado: hay quien prefiere tipear, y un
 * valor lejano al prescripto —cambiaste de mancuernas— son muchos toques. Los
 * botones son el camino rápido, no el único.
 */
function Stepper({
  etiqueta,
  valor,
  onCambio,
  paso = 1,
  decimales = false,
}: {
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  paso?: number;
  decimales?: boolean;
}) {
  const mover = (signo: number) => {
    const n = Number(valor === "" ? 0 : valor);
    if (Number.isNaN(n)) return;
    const siguiente = Math.max(0, n + signo * paso);
    onCambio(String(decimales ? Math.round(siguiente * 10) / 10 : siguiente));
  };

  return (
    <div className="stepper">
      <span className="stepper__etiqueta">{etiqueta}</span>
      <div className="stepper__control">
        <button
          type="button"
          onClick={() => mover(-1)}
          aria-label={`Bajar ${etiqueta}`}
        >
          −
        </button>
        <input
          inputMode={decimales ? "decimal" : "numeric"}
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          aria-label={etiqueta}
        />
        <button
          type="button"
          onClick={() => mover(1)}
          aria-label={`Subir ${etiqueta}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

/**
 * El descanso, que hasta ahora era un número impreso y nada más.
 *
 * Arranca solo al registrar porque es exactamente cuando empieza: nadie va a
 * apretar «iniciar descanso» con la barra todavía en la mano. No suena ni
 * vibra —eso necesita permisos y una decisión aparte—, sólo cuenta.
 */
function Descanso({ segundos }: { segundos: number }) {
  const [restan, setRestan] = useState(segundos);

  // Sin reiniciar el estado acá dentro: quien lo usa le pasa `key`, así que un
  // descanso nuevo es un componente nuevo y `useState` ya arranca donde va.
  // Poner un `setState` sincrónico en el efecto encadena renders, y además
  // duplica la fuente de verdad del valor inicial.
  useEffect(() => {
    const reloj = setInterval(() => {
      setRestan((previo) => (previo <= 1 ? 0 : previo - 1));
    }, 1000);
    return () => clearInterval(reloj);
  }, []);

  if (restan <= 0)
    return <p className="descanso descanso--listo">Descanso terminado</p>;
  const mm = Math.floor(restan / 60);
  const ss = String(restan % 60).padStart(2, "0");
  return (
    <p className="descanso" aria-live="off">
      Descanso{" "}
      <strong>
        {mm}:{ss}
      </strong>
    </p>
  );
}

/** Una serie ya registrada: un renglón, no un formulario. */
function SerieHecha({
  serie,
  onCorregir,
}: {
  serie: SerieDelDia;
  onCorregir: () => void;
}) {
  return (
    <li className="serie-fila serie-fila--hecha">
      <span className="serie-fila__numero" aria-hidden="true">
        {serie.set_number}
      </span>
      <span className="serie-fila__dato">{serie.reps_done} reps</span>
      <span className="serie-fila__dato">
        {serie.load_done_kg != null ? `${serie.load_done_kg} kg` : "—"}
      </span>
      <span className="serie-fila__dato">RIR {serie.rir_done ?? "—"}</span>
      <button type="button" className="sutil" onClick={onCorregir}>
        Corregir
      </button>
    </li>
  );
}

/** Una que todavía no llegó: se insinúa para saber cuántas faltan. */
function SeriePendiente({ serie }: { serie: SerieDelDia }) {
  return (
    <li className="serie-fila serie-fila--pendiente">
      <span className="serie-fila__numero" aria-hidden="true">
        {serie.set_number}
      </span>
      <span className="serie-fila__dato">
        {serie.reps_min ?? "?"}
        {serie.reps_max && serie.reps_max !== serie.reps_min
          ? `-${serie.reps_max}`
          : ""}{" "}
        reps
      </span>
      <span className="serie-fila__dato">
        {serie.target_load_kg != null ? `${serie.target_load_kg} kg` : "libre"}
      </span>
      <span className="serie-fila__dato">RIR {serie.rir_min ?? "?"}</span>
    </li>
  );
}

/** La única abierta. */
function SerieActual({
  serie,
  sesionId,
  descanso,
}: {
  serie: SerieDelDia;
  sesionId: string;
  descanso: number | null;
}) {
  const registrar = useRegistrarSerie(sesionId);
  const [reps, setReps] = useState(
    String(serie.reps_done ?? serie.reps_min ?? ""),
  );
  const [carga, setCarga] = useState(
    String(serie.load_done_kg ?? serie.target_load_kg ?? ""),
  );
  const [rir, setRir] = useState(String(serie.rir_done ?? serie.rir_min ?? ""));
  const [descansando, setDescansando] = useState<number | null>(null);

  const mandar = (extra: { was_skipped?: boolean } = {}) =>
    registrar.mutate(
      {
        serieId: serie.id,
        reps: reps === "" ? null : Number(reps),
        load_kg: carga === "" ? null : Number(carga),
        rir: rir === "" ? null : Number(rir),
        ...extra,
      },
      { onSuccess: () => setDescansando(descanso ? Date.now() : null) },
    );

  return (
    <li className="serie-actual">
      <p className="serie-actual__marca">Serie {serie.set_number}</p>
      <div className="serie-actual__campos">
        <Stepper etiqueta="Reps" valor={reps} onCambio={setReps} />
        <Stepper
          etiqueta="Kg"
          valor={carga}
          onCambio={setCarga}
          paso={2.5}
          decimales
        />
        <Stepper etiqueta="RIR" valor={rir} onCambio={setRir} />
      </div>
      <button
        type="button"
        className="principal serie-actual__registrar"
        onClick={() => mandar()}
        disabled={registrar.isPending}
      >
        {registrar.isPending ? "Guardando…" : "Registrar serie"}
      </button>
      <button
        type="button"
        className="sutil serie-actual__saltear"
        onClick={() => mandar({ was_skipped: true })}
        disabled={registrar.isPending}
      >
        La salté
      </button>
      {descansando && descanso ? (
        <Descanso key={descansando} segundos={descanso} />
      ) : null}
      {registrar.isError ? (
        <p className="estado estado--falla" role="alert">
          No se pudo registrar.
        </p>
      ) : null}
    </li>
  );
}

function Ejercicio({
  bloque,
  sesionId,
  abierto,
  onAbrir,
}: {
  bloque: BloqueDelDia;
  sesionId: string;
  abierto: boolean;
  onAbrir: () => void;
}) {
  const completo = bloque.sets.length > 0 && bloque.sets.every(hecha);
  // Cuál está abierta: la primera sin registrar. Si están todas hechas y la
  // persona vuelve a entrar, ninguna — el ejercicio se lee, no se completa de
  // nuevo. `corrigiendo` es la excepción explícita.
  const [corrigiendo, setCorrigiendo] = useState<string | null>(null);
  const siguiente = bloque.sets.find((s) => !hecha(s));
  const abierta = corrigiendo ?? siguiente?.id ?? null;

  if (!abierto) {
    return (
      <li>
        <button
          type="button"
          className={`ejercicio-cerrado${completo ? " ejercicio-cerrado--hecho" : ""}`}
          onClick={onAbrir}
        >
          <span className="ejercicio-cerrado__tilde" aria-hidden="true">
            {completo ? "✓" : ""}
          </span>
          <span className="ejercicio-cerrado__nombre">{bloque.exercise}</span>
          <span className="ejercicio-cerrado__objetivo">
            {objetivoDe(bloque)}
          </span>
        </button>
      </li>
    );
  }

  return (
    <li className="ejercicio-abierto">
      <div className="ejercicio-abierto__cabecera">
        <h3>{bloque.exercise}</h3>
        <span className="ejercicio-abierto__objetivo">
          {objetivoDe(bloque)}
        </span>
      </div>
      {bloque.coach_note ? (
        <p className="ejercicio-abierto__nota">{bloque.coach_note}</p>
      ) : null}
      <ul className="lista-de-series">
        {bloque.sets.map((serie) =>
          serie.id === abierta ? (
            <SerieActual
              key={serie.id}
              serie={serie}
              sesionId={sesionId}
              descanso={bloque.rest_seconds}
            />
          ) : hecha(serie) ? (
            <SerieHecha
              key={serie.id}
              serie={serie}
              onCorregir={() => setCorrigiendo(serie.id)}
            />
          ) : (
            <SeriePendiente key={serie.id} serie={serie} />
          ),
        )}
      </ul>
    </li>
  );
}

export function SesionDelDia() {
  const { sesionId } = useParams();
  const detalle = useSesion(sesionId ?? "", "athlete");
  // Cuál está abierto, sin recalcularse solo: si el ejercicio abierto saltara al
  // siguiente al terminar el último set, la pantalla se movería debajo de la
  // mano justo después de un toque.
  const [abiertoManual, setAbiertoManual] = useState<string | null>(null);
  if (!sesionId) return null;

  return (
    /* Columna angosta: esta pantalla se usa con el teléfono en la mano, y el
       marco ahora es ancho para que entre el editor. */
    <div className="columna">
      {/* Volver es una acción, no una nota al pie. Con el chevron adelante y
          altura de dedo, se aprieta sin apuntar — es la primera cosa que se toca
          al terminar un día. */}
      <Link to="/entrenar" className="volver">
        <span aria-hidden="true">‹</span> Mis sesiones
      </Link>
      <Consulta consulta={detalle} que="la sesión">
        {(datos) => {
          const completos = datos.blocks.filter(
            (b) => b.sets.length > 0 && b.sets.every(hecha),
          ).length;
          const primeroSinTerminar = datos.blocks.find(
            (b) => !(b.sets.length > 0 && b.sets.every(hecha)),
          );
          const abierto =
            abiertoManual ?? primeroSinTerminar?.prescription_id ?? null;

          return (
            <>
              <h2>
                {datos.mesocycle} · semana {datos.week_number}, día{" "}
                {datos.day_number}
              </h2>

              <div className="progreso">
                <p className="progreso__texto">
                  <strong>
                    {completos} de {datos.blocks.length}
                  </strong>{" "}
                  ejercicios completados
                </p>
                <div
                  className="progreso__barra"
                  role="progressbar"
                  aria-valuenow={completos}
                  aria-valuemin={0}
                  aria-valuemax={datos.blocks.length}
                  aria-label="Ejercicios completados"
                >
                  <span
                    style={{
                      width: datos.blocks.length
                        ? `${(completos / datos.blocks.length) * 100}%`
                        : "0%",
                    }}
                  />
                </div>
              </div>

              <ul className="lista-de-ejercicios">
                {datos.blocks.map((bloque) => (
                  <Ejercicio
                    key={bloque.prescription_id}
                    bloque={bloque}
                    sesionId={sesionId}
                    abierto={bloque.prescription_id === abierto}
                    onAbrir={() => setAbiertoManual(bloque.prescription_id)}
                  />
                ))}
              </ul>
            </>
          );
        }}
      </Consulta>
    </div>
  );
}

export function MisSesiones() {
  const fichas = useAtletas("athlete");
  return (
    <div className="columna">
      <Consulta
        consulta={fichas}
        que="tus fichas"
        vacio={{
          cuando: (lista) => lista.length === 0,
          motivo:
            "Todavía no reclamaste ninguna ficha. Pedile el link a tu entrenador.",
        }}
      >
        {(lista) =>
          lista.map((ficha) => (
            <AgendaDeUnaFicha key={ficha.id} atletaId={ficha.id} />
          ))
        }
      </Consulta>
    </div>
  );
}

/**
 * Las sesiones del atleta.
 *
 * Pasa por el listado de fichas porque una persona puede ser atleta de varios
 * entrenadores, y en ese caso tiene más de una agenda. Con una sola ficha el
 * paso es invisible: se entra directo.
 */
function AgendaDeUnaFicha({ atletaId }: { atletaId: string }) {
  const agenda = useAgenda(atletaId, "athlete");
  return (
    <section className="tarjeta">
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
          <ul className="agenda">
            {lista.map((s) => {
              // Un día está completo cuando no le queda ninguna serie sin
              // contestar. `> 0` en el denominador porque un día sin nada
              // prescripto no está terminado: está vacío, y decirle «completado»
              // sería felicitar a alguien por no hacer nada.
              const completo =
                s.series_prescritas > 0 &&
                s.series_respondidas >= s.series_prescritas;
              const empezado = s.series_respondidas > 0 && !completo;
              return (
                <li key={s.id}>
                  {/* Toda la fila es el destino, y no un texto subrayado en el
                    medio: en el teléfono se toca con el pulgar sin apuntar, y un
                    enlace de dos palabras dentro de un renglón vacío es un
                    objetivo de doce píxeles rodeado de nada. */}
                  <Link
                    to={`/entrenar/${s.id}`}
                    className={`agenda__dia${completo ? " agenda__dia--completo" : ""}`}
                  >
                    <span className="agenda__numero" aria-hidden="true">
                      {completo ? "✓" : `D${s.day_number}`}
                    </span>
                    <span className="agenda__texto">
                      <strong>Día {s.day_number}</strong>
                      <small>
                        {s.mesocycle} · semana {s.week_number}
                        {/* El estado va en palabras y no sólo en el color: quien no
                          distingue los tonos tiene que poder leerlo, y a pleno
                          sol tampoco se ve un verde de otro gris. */}
                        {completo ? " · completado" : null}
                        {empezado
                          ? ` · ${s.series_respondidas} de ${s.series_prescritas}`
                          : null}
                      </small>
                    </span>
                    <span className="agenda__flecha" aria-hidden="true">
                      ›
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Consulta>
    </section>
  );
}
