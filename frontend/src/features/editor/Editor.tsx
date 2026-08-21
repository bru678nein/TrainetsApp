import { useState } from "react";

import { ErrorDelApi } from "../../api/cliente";
import {
  useEjercicios,
  useEscrituraDelEditor,
  useMesociclos,
  usePatrones,
  useProgramas,
  useProyeccion,
  useSesion,
  type Ejercicio,
  type EjercicioProyectado,
  type Mesociclo,
  type Patron,
  type Programa,
  type SemanaProyectada,
  type SerieProyectada,
  type SesionDeLaAgenda,
} from "../../api/consultas";
import { Cargando, Consulta, Falla, Vacio } from "../../components/estados";
import { Mas, Tacho } from "../../components/iconos";
import { Confirmar } from "../../components/Confirmar";
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

function NuevoMesociclo({
  programaId,
  siguiente,
}: {
  programaId: string;
  siguiente: number;
}) {
  const [label, setLabel] = useState("");
  const [semanas, setSemanas] = useState(4);
  const [progresion, setProgresion] = useState("0, 0, -1, -1");

  const crear = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/programs/${programaId}/mesocycles`, {
        ordinal: siguiente,
        label: label.trim(),
        week_count: semanas,
        rir_progression: progresion.trim()
          ? progresion.split(",").map((n) => Number(n.trim()))
          : null,
      }),
    "Mesociclo creado",
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
        Nombre{" "}
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          required
        />
      </label>{" "}
      <Selector
        etiqueta="Semanas"
        valor={semanas}
        onCambio={setSemanas}
        max={16}
      />
      <label title="Cuánto se mueve el RIR en cada semana, respecto de la primera">
        Progresión de RIR{" "}
        <input
          value={progresion}
          onChange={(e) => setProgresion(e.target.value)}
        />
      </label>{" "}
      <button
        type="submit"
        className="principal"
        disabled={crear.isPending || !label.trim()}
      >
        Crear
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

  const crear = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/prescriptions/${prescripcionId}/sets`, {
        reps_min: reps ? Number(reps) : null,
        reps_max: reps ? Number(reps) : null,
        rir_min: rir ? Number(rir) : null,
        rir_max: rir ? Number(rir) : null,
        // Sin carga es autorregulada: el peso lo elige el atleta ese día. No se
        // manda cero, que sería una barra vacía y cuenta como carga en el tonelaje.
        target_load_kg: carga ? Number(carga) : null,
      }),
    "Serie agregada",
  );

  return (
    <form
      className="serie-nueva"
      onSubmit={(e) => {
        e.preventDefault();
        crear.mutate();
      }}
    >
      {/* Las etiquetas van arriba y visibles, no en el `placeholder`. Un
          `placeholder` desaparece al escribir: después de tipear tres números
          quedan tres cajas iguales y nadie sabe cuál era el RIR. */}
      <label className="campo">
        <span>Reps</span>
        <input
          inputMode="numeric"
          value={reps}
          onChange={(e) => setReps(e.target.value)}
        />
      </label>
      <label className="campo">
        <span>RIR</span>
        <input
          inputMode="decimal"
          value={rir}
          onChange={(e) => setRir(e.target.value)}
        />
      </label>
      <label className="campo">
        <span>Kg</span>
        <input
          inputMode="decimal"
          value={carga}
          onChange={(e) => setCarga(e.target.value)}
          placeholder="libre"
        />
      </label>
      <button type="submit" className="principal" disabled={crear.isPending}>
        Agregar serie
      </button>
      {/* Dejar el peso vacío es una prescripción válida y no un olvido, así que
          se dice acá en vez de que alguien lo descubra. */}
      <small className="serie-nueva__nota">
        Sin kg, el peso lo elige el atleta.
      </small>
      <Aviso de={crear} />
    </form>
  );
}

function ContenidoDeSesion({ sesionId }: { sesionId: string }) {
  const detalle = useSesion(sesionId, "coach");
  const ejercicios = useEjercicios();
  const patrones = usePatrones();
  const [elegido, setElegido] = useState("");
  // El patrón acá **no se guarda**: la prescripción sólo apunta al ejercicio, y
  // el ejercicio ya trae el suyo. Pedir los dos sería pedir dos veces el mismo
  // dato y dejar que se contradigan — una sentadilla cargada como empuje
  // vertical rompe el análisis de volumen sin que nada avise.
  //
  // Sirve para encontrar: son cincuenta y nueve ejercicios en un desplegable
  // plano, y el patrón es la forma en que el entrenador ya los piensa.
  const [patronFiltro, setPatronFiltro] = useState("");

  // El esquema con el que nace el ejercicio. Medido sobre la programación real:
  // 473 de 473 ejercicios prescriptos tienen todas sus series idénticas, y 324
  // de ellos son de tres series. Así que el formulario pide el esquema una vez
  // y no una fila por serie — eran 84 de las 105 interacciones de un día.
  const [series, setSeries] = useState(3);
  const [reps, setReps] = useState("8");
  const [rir, setRir] = useState("2");
  const [carga, setCarga] = useState("");

  const agregar = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/sessions/${sesionId}/prescriptions`, {
        exercise_id: elegido,
        // La misma serie repetida N veces, y no un "cantidad + esquema": que sean
        // todas iguales es un hecho de estos datos y no una regla, y el día que
        // una difiera la API ya lo acepta.
        sets: Array.from({ length: series }, () => ({
          reps_min: reps ? Number(reps) : null,
          reps_max: reps ? Number(reps) : null,
          rir_min: rir ? Number(rir) : null,
          rir_max: rir ? Number(rir) : null,
          // Sin carga es autorregulada: el peso lo elige el atleta ese día.
          target_load_kg: carga ? Number(carga) : null,
        })),
      }),
    // Nombra las dos cosas que pasaron. «Ejercicio agregado» a secas dejaría
    // dudando de si las series se crearon, que es justo lo que cambió.
    `Ejercicio agregado con ${series} series`,
  );
  const borrarSerie = useEscrituraDelEditor<unknown, string>(
    (_, mutar, id) => mutar("DELETE", `/api/prescribed-sets/${id}`),
    "Serie borrada",
  );
  const borrarEjercicio = useEscrituraDelEditor<unknown, string>(
    (_, mutar, id) => mutar("DELETE", `/api/prescriptions/${id}`),
    "Ejercicio sacado del día",
  );
  const duplicarEjercicio = useEscrituraDelEditor<unknown, string>(
    (enviar, _, id) => enviar(`/api/prescriptions/${id}/duplicate`),
    "Ejercicio duplicado",
  );
  const reordenar = useEscrituraDelEditor<unknown, string[]>(
    (_, mutar, ids) =>
      mutar("PUT", `/api/sessions/${sesionId}/prescriptions/order`, { ids }),
    "Orden guardado",
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
                elementos={datos.blocks.map((b) => ({
                  ...b,
                  id: b.prescription_id,
                }))}
                onOrdenar={(ids) => reordenar.mutate(ids)}
                deshabilitado={reordenar.isPending}
              >
                {(bloque) => (
                  <>
                    <div className="ejercicio__cabecera">
                      <strong className="ejercicio__nombre">
                        {bloque.exercise}
                      </strong>
                      <span className="chip">{bloque.pattern}</span>
                      <span className="empuja" />
                      {/* Calladas y a la derecha: el nombre del ejercicio es lo
                          que se lee, y dos botones con peso al lado se lo
                          comen. */}
                      <button
                        type="button"
                        className="sutil"
                        onClick={() =>
                          duplicarEjercicio.mutate(bloque.prescription_id)
                        }
                      >
                        Duplicar
                      </button>
                      <button
                        type="button"
                        className="sutil ejercicio__borrar"
                        onClick={() =>
                          borrarEjercicio.mutate(bloque.prescription_id)
                        }
                        aria-label={`Sacar ${bloque.exercise} de este día`}
                        title="Sacar de este día"
                      >
                        <Tacho />
                      </button>
                    </div>
                    <ul className="lista">
                      {bloque.sets.map((serie) => (
                        <li key={serie.id} className="serie">
                          <span className="serie__numero">
                            {serie.set_number}
                          </span>
                          <span className="serie__dato">
                            <strong>
                              {serie.reps_min ?? "?"}
                              {serie.reps_max &&
                              serie.reps_max !== serie.reps_min
                                ? `-${serie.reps_max}`
                                : ""}
                            </strong>{" "}
                            reps
                          </span>
                          <span className="serie__dato">
                            RIR <strong>{serie.rir_min ?? "?"}</strong>
                          </span>
                          <span className="serie__dato">
                            {serie.target_load_kg != null ? (
                              <>
                                <strong>{serie.target_load_kg}</strong> kg
                              </>
                            ) : (
                              "peso a elección"
                            )}
                          </span>
                          <span className="empuja" />
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
            className="alta-de-ejercicio"
            onSubmit={(e) => {
              e.preventDefault();
              if (elegido) agregar.mutate();
            }}
          >
            <select
              value={patronFiltro}
              aria-label="Filtrar por patrón de movimiento"
              onChange={(e) => {
                setPatronFiltro(e.target.value);
                // Lo elegido puede no estar en el patrón nuevo, y un `select`
                // con un valor que no figura entre sus opciones se dibuja vacío
                // pero manda el viejo al enviar.
                setElegido("");
              }}
            >
              <option value="">Todos los patrones</option>
              {(patrones.data ?? []).map((p) => (
                <option key={p.code} value={p.code}>
                  {p.label_es}
                </option>
              ))}
            </select>
            <select
              value={elegido}
              aria-label="Ejercicio"
              onChange={(e) => setElegido(e.target.value)}
            >
              <option value="">— elegí un ejercicio —</option>
              {lista
                .filter(
                  (ej) => !patronFiltro || ej.pattern_code === patronFiltro,
                )
                .map((ej) => (
                  <option key={ej.id} value={ej.id}>
                    {ej.name}
                  </option>
                ))}
            </select>
            {/* Las etiquetas arriba y visibles, no en el `placeholder`: un
                `placeholder` desaparece al escribir y quedan cuatro cajas de
                números iguales sin saber cuál era el RIR. */}
            <Selector
              etiqueta="Series"
              valor={series}
              onCambio={setSeries}
              max={8}
            />
            <label className="campo">
              <span>Reps</span>
              <input
                inputMode="numeric"
                value={reps}
                onChange={(e) => setReps(e.target.value)}
              />
            </label>
            <label className="campo">
              <span>RIR</span>
              <input
                inputMode="decimal"
                value={rir}
                onChange={(e) => setRir(e.target.value)}
              />
            </label>
            <label className="campo">
              <span>Kg</span>
              <input
                inputMode="decimal"
                value={carga}
                onChange={(e) => setCarga(e.target.value)}
                placeholder="libre"
              />
            </label>
            <button
              type="submit"
              className="principal"
              disabled={!elegido || agregar.isPending}
            >
              Agregar ejercicio
            </button>
            <small className="serie-nueva__nota">
              Se crean {series} series iguales. Sin kg, el peso lo elige el
              atleta.
            </small>
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

type Filtro = "todo" | "ejercicios" | "patrones";

const FILTROS: { id: Filtro; titulo: string }[] = [
  { id: "todo", titulo: "Todo" },
  { id: "ejercicios", titulo: "Ejercicios" },
  { id: "patrones", titulo: "Patrones" },
];

/** Sin acentos y en minúsculas, para que buscar "pliometria" encuentre "PLIOMETRIA". */
const plano = (texto: string) =>
  texto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

function AgregarEjercicio() {
  const patrones = usePatrones();
  const [nombre, setNombre] = useState("");
  const [patron, setPatron] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar("/api/exercises", { name: nombre.trim(), pattern_code: patron }),
    "Ejercicio agregado al catálogo",
  );

  return (
    <section className="tarjeta">
      <h3>Agregar un ejercicio</h3>
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
              Agregar
            </button>
          </form>
        )}
      </Consulta>
      <small>
        El patrón es obligatorio: sin él no hay análisis de volumen.
      </small>
      <Aviso de={crear} />
    </section>
  );
}

function AgregarPatron() {
  const [nombre, setNombre] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>(
    (enviar) => enviar("/api/movement-patterns", { label_es: nombre.trim() }),
    "Patrón creado",
  );

  return (
    <section className="tarjeta">
      <h3>Agregar un patrón de movimiento</h3>
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
          placeholder="Aducción de cadera"
          aria-label="Nombre del patrón"
          required
        />
        <button type="submit" disabled={!nombre.trim() || crear.isPending}>
          Agregar
        </button>
      </form>
      {/* Conviene decirlo antes y no descubrirlo después: la tabla no tiene
          dueño, y que sea compartida es lo que permite comparar volumen por
          patrón entre atletas. */}
      <small>Es tuyo: no aparece en el catálogo de otros entrenadores.</small>
      <Aviso de={crear} />
    </section>
  );
}

function FilaDeEjercicio({
  ej,
  nombreDe,
}: {
  ej: Ejercicio;
  nombreDe: (c: string) => string;
}) {
  const patrones = usePatrones();
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(ej.name);
  const [patron, setPatron] = useState(ej.pattern_code);

  const guardar = useEscrituraDelEditor<unknown, void>(
    (_, mutar) =>
      mutar("PATCH", `/api/exercises/${ej.id}`, {
        name: nombre.trim(),
        pattern_code: patron,
      }),
    "Ejercicio guardado",
  );
  const [confirmando, setConfirmando] = useState(false);
  const borrar = useEscrituraDelEditor<unknown, void>(
    (_, mutar) =>
      // `confirmar` va en la llamada porque la API se niega por defecto a sacar un
      // ejercicio de los días que lo incluyen: un cliente que no pregunte no
      // arrasa un programa por descuido.
      mutar("DELETE", `/api/exercises/${ej.id}?confirmar=true`),
    "Ejercicio borrado",
  );

  // El catálogo global se lee y no se toca: es de todos y se modifica con una
  // migración. Ofrecer los botones sería prometer algo que el servidor rechaza.
  const propio = ej.coach_id !== null;

  if (editando) {
    return (
      <li className="catalogo__ficha">
        <form
          className="fila"
          onSubmit={(e) => {
            e.preventDefault();
            guardar.mutate(undefined, { onSuccess: () => setEditando(false) });
          }}
        >
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            aria-label={`Nombre de ${ej.name}`}
            required
          />
          <select
            value={patron}
            onChange={(e) => setPatron(e.target.value)}
            aria-label={`Patrón de ${ej.name}`}
          >
            {(patrones.data ?? []).map((p) => (
              <option key={p.code} value={p.code}>
                {p.label_es}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="principal"
            disabled={guardar.isPending}
          >
            Guardar
          </button>
          <button
            type="button"
            className="sutil"
            onClick={() => setEditando(false)}
          >
            Cancelar
          </button>
        </form>
        <Aviso de={guardar} />
      </li>
    );
  }

  return (
    <li className="catalogo__ficha">
      <div className="fila">
        <strong>{ej.name}</strong>
        <span className="chip">{nombreDe(ej.pattern_code)}</span>
        <span className="empuja" />
        {propio ? (
          <>
            <button
              type="button"
              className="sutil catalogo__accion"
              onClick={() => setEditando(true)}
              aria-label={`Editar ${ej.name}`}
            >
              Editar
            </button>
            <button
              type="button"
              className="sutil catalogo__accion"
              onClick={() => setConfirmando(true)}
              disabled={borrar.isPending}
              aria-label={`Borrar ${ej.name}`}
            >
              <Tacho />
            </button>
            <Confirmar
              abierto={confirmando}
              titulo={`Borrar «${ej.name}»`}
              onCancelar={() => setConfirmando(false)}
              onConfirmar={() => {
                setConfirmando(false);
                borrar.mutate();
              }}
            >
              {ej.prescription_count > 0 ? (
                <p>
                  Está en <strong>{ej.prescription_count}</strong>{" "}
                  {ej.prescription_count === 1 ? "día" : "días"} y se va a sacar
                  de todos.{" "}
                  {/* La mitad que tranquiliza, y es cierta por la 0016: el
                      registro del atleta sobrevive con su copia de lo que se le
                      pidió, aunque el plan ya no exista. */}
                  Lo que tu atleta ya registró no se pierde.
                </p>
              ) : (
                <p>No está prescrito en ningún día.</p>
              )}
            </Confirmar>
          </>
        ) : (
          <small>global</small>
        )}
      </div>
      <Aviso de={borrar} />
    </li>
  );
}

function FilaDePatron({ patron }: { patron: Patron }) {
  const [confirmando, setConfirmando] = useState(false);
  const borrar = useEscrituraDelEditor<unknown, void>(
    (_, mutar) => mutar("DELETE", `/api/movement-patterns/${patron.code}`),
    "Patrón borrado",
  );
  // La base común se lee. Ofrecer el botón sería prometer un 403.
  const propio = Boolean(patron.coach_id);

  return (
    <li className="catalogo__ficha">
      <div className="fila">
        <strong>{patron.label_es}</strong>
        {/* La etiqueta dice qué es. En una lista mezclada, «Bíceps» suelto se
            lee como un ejercicio. */}
        <span className="chip chip--patron">patrón</span>
        <span className="empuja" />
        {propio ? (
          <button
            type="button"
            className="sutil catalogo__accion"
            onClick={() => setConfirmando(true)}
            disabled={borrar.isPending}
            aria-label={`Borrar el patrón ${patron.label_es}`}
          >
            <Tacho />
          </button>
        ) : (
          <small>base común</small>
        )}
      </div>
      <Confirmar
        abierto={confirmando}
        titulo={`Borrar el patrón «${patron.label_es}»`}
        onCancelar={() => setConfirmando(false)}
        onConfirmar={() => {
          setConfirmando(false);
          borrar.mutate();
        }}
      >
        <p>Los ejercicios que lo usen tienen que cambiar de patrón antes.</p>
      </Confirmar>
      <Aviso de={borrar} />
    </li>
  );
}

function Catalogo() {
  const patrones = usePatrones();
  const ejercicios = useEjercicios();
  const nombreDe = useNombreDePatron();
  const [filtro, setFiltro] = useState<Filtro>("todo");
  const [busqueda, setBusqueda] = useState("");

  const coincide = (texto: string) =>
    plano(texto).includes(plano(busqueda.trim()));
  const ejercisFiltrados = (ejercicios.data ?? []).filter((e) =>
    coincide(e.name),
  );
  const patronesFiltrados = (patrones.data ?? []).filter((p) =>
    coincide(p.label_es),
  );

  const verEjercicios = filtro !== "patrones";
  const verPatrones = filtro !== "ejercicios";
  const vacio =
    (verEjercicios ? ejercisFiltrados.length : 0) +
      (verPatrones ? patronesFiltrados.length : 0) ===
    0;

  return (
    <>
      <AgregarEjercicio />
      <AgregarPatron />

      <section className="tarjeta">
        <h3>El catálogo</h3>
        <div className="fila catalogo__controles">
          <input
            type="search"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar…"
            aria-label="Buscar en el catálogo"
          />
          <div className="fila" role="group" aria-label="Filtrar el catálogo">
            {FILTROS.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={filtro === f.id}
                className={filtro === f.id ? "principal" : undefined}
                onClick={() => setFiltro(f.id)}
              >
                {f.titulo}
              </button>
            ))}
          </div>
        </div>

        {vacio ? (
          <Vacio
            motivo={
              busqueda.trim()
                ? `No hay nada que coincida con «${busqueda.trim()}».`
                : "El catálogo está vacío. Agregá el primer ejercicio acá arriba."
            }
          />
        ) : (
          // Con nombre: en la pestaña hay dos formularios cuyos desplegables
          // repiten los mismos textos, y sin él la lista no se puede nombrar
          // ni desde un lector de pantalla ni desde un test.
          <ul className="catalogo" aria-label="Catálogo">
            {verEjercicios &&
              ejercisFiltrados.map((ej) => (
                <FilaDeEjercicio key={ej.id} ej={ej} nombreDe={nombreDe} />
              ))}
            {verPatrones &&
              patronesFiltrados.map((p) => (
                <FilaDePatron key={p.code} patron={p} />
              ))}
          </ul>
        )}
      </section>
    </>
  );
}

// --- La pantalla ----------------------------------------------------------------

function NuevoPrograma({ atletaId }: { atletaId: string }) {
  const [nombre, setNombre] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/athletes/${atletaId}/programs`, { name: nombre.trim() }),
    "Programa creado",
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
      <button
        type="submit"
        className="principal"
        disabled={!nombre.trim() || crear.isPending}
      >
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
/**
 * Cuánto mueve el RIR pasar de una semana a otra dentro del bloque.
 *
 * La progresión se guarda como desplazamientos absolutos contra la primera
 * semana, así que ir de W a T aplica la **diferencia**. Lo que falte en la lista
 * se lee como cero, igual que en el servidor: un bloque que se extendió y no
 * declaró las semanas nuevas no progresa en ellas.
 *
 * Vive acá una sola vez. Estaba escrita dos —en el botón de pegar y a punto de
 * estarlo en el riel— y dos copias de una regla aritmética se separan sin que
 * nada falle: siguen dando un número, sólo que el equivocado.
 *
 * Esto lee la **declaración**, que el mesociclo ya trae. Lo que no se calcula
 * acá es la proyección del contenido —qué series quedan— porque eso sí es la
 * regla del servidor y tiene su endpoint.
 */
function desplazamiento(meso: Mesociclo, desde: number, hasta: number): number {
  const tabla = meso.rir_progression;
  if (!tabla) return 0;
  return (tabla[hasta - 1] ?? 0) - (tabla[desde - 1] ?? 0);
}

/**
 * El paso de una semana contra la anterior, telegráfico.
 *
 * Corto a propósito: el riel y la proyección pueden estar en pantalla a la vez,
 * y con la misma frase en los dos lados uno de los dos sobra. El riel dice el
 * paso, la proyección dice qué produce.
 */
function pasoDelRiel(meso: Mesociclo, numero: number): string {
  if (numero === 1) return "base";
  const salto = desplazamiento(meso, numero - 1, numero);
  if (salto === 0) return "igual";
  return salto < 0 ? `−${Math.abs(salto)} RIR` : `+${salto} RIR`;
}

function Semana({
  meso,
  numero,
  sesiones,
  abierta,
  onAbrir,
  semanasArmadas,
}: {
  meso: Mesociclo;
  numero: number;
  sesiones: SesionDeLaAgenda[];
  abierta: string | null;
  onAbrir: (id: string | null) => void;
  /** Cuáles ya tienen días: son las que no se pueden pisar. */
  semanasArmadas: number[];
}) {
  // La semana que se está editando ocupa el ancho entero. Media pantalla alcanza
  // para leer qué días tiene, y no para armar un ejercicio con sus series: ahí
  // todo se parte en tres renglones y deja de entenderse.
  const editando = sesiones.some((s) => s.id === abierta);
  const usados = new Set(sesiones.map((s) => s.day_number));
  const siguiente = [1, 2, 3, 4, 5, 6, 7].find((d) => !usados.has(d));

  const agregar = useEscrituraDelEditor<unknown, number>(
    (enviar, _, dia) =>
      enviar(`/api/mesocycles/${meso.id}/sessions`, {
        week_number: numero,
        day_number: dia,
      }),
    "Día agregado",
  );
  const borrar = useEscrituraDelEditor<unknown, string>(
    (_, mutar, id) => mutar("DELETE", `/api/sessions/${id}`),
    "Día borrado",
  );
  // A qué semanas se puede duplicar: sólo las vacías. El servidor rechaza con
  // 409 pisar una semana armada —el atleta pudo haber registrado series ahí— así
  // que no se ofrece un destino que va a contestar un error.
  const destinos = Array.from(
    { length: meso.week_count },
    (_, i) => i + 1,
  ).filter((n) => n !== numero && !semanasArmadas.includes(n));
  const [destino, setDestino] = useState<number | null>(null);
  const elegido =
    destino !== null && destinos.includes(destino)
      ? destino
      : (destinos[0] ?? null);

  const pegar = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/mesocycles/${meso.id}/duplicate-week`, {
        from_week: numero,
        to_week: elegido,
      }),
    "Semana duplicada",
  );

  // Cuánto mueve el RIR caer en el destino. Es la razón por la que duplicar
  // sirve, y decirlo antes de apretar lo convierte en una decisión.
  const salto = elegido !== null ? desplazamiento(meso, numero, elegido) : null;

  return (
    <section
      className={`semana${editando ? " semana--editando" : ""}`}
    >
      <div className="semana__cabecera">
        <h4 className="semana__titulo">Semana {numero}</h4>
        <span className="semana__cuenta">
          {sesiones.length === 0
            ? "sin días"
            : `${sesiones.length} ${sesiones.length === 1 ? "día" : "días"}`}
        </span>
      </div>

      {/* Duplicar es la acción más usada del producto, así que vive como una
          barra fija arriba de la semana y no como un ítem de menú.

          Reemplazó a copiar y pegar, que eran dos pasos en dos semanas
          distintas: acá el destino se elige en el mismo lugar donde se aprieta,
          y el salto de RIR se dice antes, que convierte duplicar en una decisión
          en vez de una sorpresa. */}
      {sesiones.length > 0 && destinos.length > 0 ? (
        <div className="duplicar">
          <svg
            className="duplicar__icono"
            width="18"
            height="18"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <rect x="2.5" y="2.5" width="8" height="8" rx="1.5" />
            <path d="M5.5 13.5h6a2 2 0 0 0 2-2v-6" />
          </svg>
          <strong>Duplicar</strong>
          <label className="duplicar__destino">
            en la{" "}
            <select
              value={elegido ?? ""}
              onChange={(e) => setDestino(Number(e.target.value))}
              aria-label="Semana de destino"
            >
              {destinos.map((d) => (
                <option key={d} value={d}>
                  Semana {d}
                </option>
              ))}
            </select>
          </label>
          {salto !== null && salto !== 0 ? (
            <span className="chip chip--activo">
              <i className="chip__punto" aria-hidden="true" />
              aplica {salto > 0 ? `+${salto}` : salto} RIR
            </span>
          ) : (
            <span className="chip">sin cambio de RIR</span>
          )}
          <button
            type="button"
            className="principal"
            onClick={() => pegar.mutate()}
            disabled={pegar.isPending}
          >
            {pegar.isPending ? "Duplicando…" : "Duplicar la semana"}
          </button>
        </div>
      ) : null}

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
        title={
          siguiente
            ? `Agregar el día ${siguiente}`
            : "Esta semana ya tiene los siete días"
        }
      >
        <Mas /> {siguiente ? `Día ${siguiente}` : "Semana completa"}
      </button>
      <Aviso de={agregar} />
      <Aviso de={borrar} />
      <Aviso de={pegar} />
    </section>
  );
}

/** Cómo se lee el paso de una semana a la anterior, en palabras. */
function pasoEnPalabras(
  semana: SemanaProyectada,
  anterior: SemanaProyectada | undefined,
): string {
  if (semana.movimiento === "base") return "arranca acá";
  const salto = Math.abs(semana.rir_delta - (anterior?.rir_delta ?? 0));
  if (semana.movimiento === "sostiene") return "igual que la anterior";
  if (semana.movimiento === "aprieta")
    return `−${salto} RIR: más cerca del fallo`;
  return `+${salto} RIR: descarga`;
}

const rango = (min: number | null, max: number | null): string | null => {
  if (min === null && max === null) return null;
  if (min !== null && max !== null && min !== max) return `${min}-${max}`;
  return String(min ?? max);
};

/**
 * Las series repetidas se juntan en una línea.
 *
 * De 473 ejercicios prescritos en la planilla, los 473 tienen todas sus series
 * iguales. Listarlas una debajo de la otra es escribir cuatro veces lo mismo y
 * empujar la semana siguiente fuera de la pantalla.
 */
function agrupar(
  sets: SerieProyectada[],
): { cuantas: number; serie: SerieProyectada }[] {
  const clave = (s: SerieProyectada) =>
    JSON.stringify([
      s.reps_min,
      s.reps_max,
      s.rir_min,
      s.rir_max,
      s.target_load_kg,
      s.is_amrap,
    ]);
  const grupos: { cuantas: number; serie: SerieProyectada }[] = [];
  for (const s of sets) {
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && clave(ultimo.serie) === clave(s)) ultimo.cuantas += 1;
    else grupos.push({ cuantas: 1, serie: s });
  }
  return grupos;
}

function LineaDeEjercicio({ ej }: { ej: EjercicioProyectado }) {
  return (
    <li className="proyeccion__ejercicio">
      <span className="proyeccion__nombre">
        {ej.superset_key ? (
          <em className="proyeccion__llave">{ej.superset_key}</em>
        ) : null}
        {ej.exercise_name}
      </span>
      <ul className="proyeccion__series">
        {agrupar(ej.sets).map(({ cuantas, serie }, i) => {
          const reps = rango(serie.reps_min, serie.reps_max);
          const rir = rango(serie.rir_min, serie.rir_max);
          return (
            <li key={i}>
              {cuantas}×{reps ? ` ${reps} reps` : " serie"}
              {serie.is_amrap ? " al máximo" : ""}
              {serie.target_load_kg !== null
                ? ` · ${serie.target_load_kg} kg`
                : ""}
              {/* El RIR va marcado porque es lo único que la progresión mueve:
                  la carga y las reps se copian iguales a propósito. */}
              {rir !== null ? (
                <strong className="proyeccion__rir"> · RIR {rir}</strong>
              ) : null}
            </li>
          );
        })}
      </ul>
    </li>
  );
}

/**
 * Lo que la progresión va a producir, antes de que nadie duplique nada.
 *
 * Hasta acá la única forma de ver qué hacía una progresión declarada era
 * aplicarla: declarar `[0, 0, -1, -1]` y enterarse cuatro semanas después de que
 * no era eso, con el atleta ya entrenando encima.
 *
 * Las semanas ya armadas muestran **lo que tienen**, no una predicción. Una
 * semana duplicada se corrige a mano, y dibujarle la proyección encima mostraría
 * una semana que no existe.
 */
function PanelDeProyeccion({
  meso,
  onCerrar,
}: {
  meso: Mesociclo;
  onCerrar: () => void;
}) {
  const proyeccion = useProyeccion(meso.id, true);

  return (
    <div className="proyeccion">
      <div className="proyeccion__titulo">
        <h4>Proyección · {meso.label}</h4>
        <button
          type="button"
          className="sutil"
          onClick={onCerrar}
          aria-label="Cerrar la proyección"
        >
          ✕
        </button>
      </div>
      <Consulta consulta={proyeccion} que="la proyección">
        {(datos) =>
          datos.semana_base === null ? (
            <p className="proyeccion__vacia">
              Todavía no hay nada armado en este bloque. Cargá una semana y acá
              vas a ver cómo queda el resto.
            </p>
          ) : (
            <ol className="proyeccion__semanas">
              {datos.semanas.map((semana, i) => (
                <li
                  key={semana.week_number}
                  className={`proyeccion__semana proyeccion__semana--${semana.movimiento}`}
                >
                  <p className="proyeccion__cabecera">
                    <strong>Semana {semana.week_number}</strong>
                    <span className="proyeccion__paso">
                      {pasoEnPalabras(semana, datos.semanas[i - 1])}
                    </span>
                    {semana.ya_armada ? (
                      <span
                        className="proyeccion__armada"
                        title="Esto es lo que hay guardado"
                      >
                        armada
                      </span>
                    ) : null}
                  </p>
                  <ul className="proyeccion__dias">
                    {semana.dias.map((dia) => (
                      <li key={dia.day_number}>
                        <span className="proyeccion__dia">
                          Día {dia.day_number}
                          {dia.label ? ` — ${dia.label}` : ""}
                        </span>
                        <ul>
                          {dia.ejercicios.map((ej) => (
                            <LineaDeEjercicio key={ej.position} ej={ej} />
                          ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          )
        }
      </Consulta>
    </div>
  );
}

function Bloque({
  meso,
  atletaId,
  cuantos,
  copiado,
  onCopiar,
  proyectando,
  onProyectar,
}: {
  meso: Mesociclo;
  atletaId: string;
  cuantos: number;
  copiado: string | null;
  onCopiar: (id: string | null) => void;
  proyectando: string | null;
  onProyectar: (id: string | null) => void;
}) {
  const agenda = useAgenda(atletaId, "coach");
  const [abierta, setAbierta] = useState<string | null>(null);
  // Qué semana está abierta abajo del riel. Una sola: con las cuatro abiertas a
  // la vez había que scrollear para comparar el día 1 de dos semanas, que es la
  // comparación que el entrenador hace todo el tiempo.
  const [semanaAbierta, setSemanaAbierta] = useState(1);
  const semanas = Array.from({ length: meso.week_count }, (_, i) => i + 1);

  const duplicar = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/mesocycles/${meso.id}/duplicate`, { to_mesocycle: null }),
    "Bloque duplicado",
  );
  const pegarBloque = useEscrituraDelEditor<unknown, void>(
    (enviar) =>
      enviar(`/api/mesocycles/${copiado}/duplicate`, { to_mesocycle: meso.id }),
    "Bloque pegado",
  );

  const esteCopiado = copiado === meso.id;

  return (
    <section className={`tarjeta${esteCopiado ? " bloque--copiado" : ""}`}>
      <div className="bloque__cabecera">
        <h3>
          {meso.ordinal}. {meso.label} — {meso.week_count} semanas
        </h3>
        <button
          type="button"
          className="sutil"
          onClick={() => duplicar.mutate()}
          disabled={duplicar.isPending}
          title="Crea un bloque nuevo al final, con todo lo de éste"
        >
          {duplicar.isPending ? "Duplicando…" : "Duplicar el bloque"}
        </button>
        {/* Copiar aparece recién con más de un bloque: con uno solo no hay dónde
            pegar, y un botón que no lleva a ningún lado es ruido. Para crear el
            segundo está «Duplicar», que es un toque en vez de dos. */}
        {cuantos > 1 ? (
          <button
            type="button"
            className="sutil"
            onClick={() => onCopiar(esteCopiado ? null : meso.id)}
            aria-pressed={esteCopiado}
            aria-label={
              esteCopiado
                ? `Soltar el bloque ${meso.label}`
                : `Copiar el bloque ${meso.label}`
            }
          >
            {esteCopiado ? "Copiado" : "Copiar"}
          </button>
        ) : null}
      </div>
      <p className="bloque__progresion">
        {meso.rir_progression ? (
          <>
            Progresión declarada:{" "}
            <strong>[{meso.rir_progression.join(", ")}]</strong>
          </>
        ) : (
          <>
            Este bloque no declara progresión: pegar una semana la copia igual.
          </>
        )}{" "}
        {/* Enciende el panel de la pantalla en vez de abrir uno propio: la
            proyección es una sola y muestra el bloque que se esté mirando. Dos
            abiertas serían dos futuros distintos en la misma pantalla. */}
        <button
          type="button"
          className="sutil"
          aria-pressed={proyectando === meso.id}
          onClick={() => onProyectar(proyectando === meso.id ? null : meso.id)}
        >
          {proyectando === meso.id
            ? "Ocultar la proyección"
            : "Ver la proyección"}
        </button>
      </p>
      <Consulta consulta={agenda} que="las sesiones">
        {(todas) => {
          // Por id y no por nombre: la etiqueta la escribe el entrenador y puede
          // repetirla, y esta agenda trae las sesiones de todos sus programas.
          // Agrupando por nombre, un bloque vacío se veía lleno con las sesiones
          // de otro que se llamaba igual — y pegar no aparecía nunca.
          const mias = todas.filter((s) => s.mesocycle_id === meso.id);
          // Igual que con las semanas: sólo se pega en un bloque vacío. El
          // servidor rechaza pisar uno armado con 409, y el atleta puede haber
          // registrado series ahí.
          const sePuedePegar =
            copiado !== null && !esteCopiado && mias.length === 0;
          return (
            <div className="cuerpo-del-bloque">
              {sePuedePegar ? (
                <p className="bloque__pegar">
                  <button
                    type="button"
                    className="principal"
                    onClick={() =>
                      pegarBloque.mutate(undefined, {
                        onSuccess: () => onCopiar(null),
                      })
                    }
                    disabled={pegarBloque.isPending}
                  >
                    {pegarBloque.isPending
                      ? "Pegando…"
                      : "Pegar el bloque copiado acá"}
                  </button>
                </p>
              ) : null}
              {/* El riel: las cuatro semanas siempre a la vista, armadas y
                  vacías por igual. En una lista de lo que hay, lo que falta no
                  ocupa lugar y no se ve — y lo que falta es justamente lo que el
                  entrenador viene a hacer. */}
              <ol className="riel" aria-label={`Semanas de ${meso.label}`}>
                {semanas.map((numero) => {
                  const dias = mias.filter((s) => s.week_number === numero);
                  const abiertaEsta = semanaAbierta === numero;
                  const aprieta =
                    numero > 1 && desplazamiento(meso, numero - 1, numero) < 0;
                  return (
                    <li key={numero}>
                      <button
                        type="button"
                        className={`riel__semana${abiertaEsta ? " riel__semana--abierta" : ""}`}
                        aria-current={abiertaEsta ? "true" : undefined}
                        onClick={() => setSemanaAbierta(numero)}
                      >
                        <span className="riel__titulo">
                          Semana {numero}
                          {dias.length > 0 ? (
                            <span className="chip">armada</span>
                          ) : null}
                        </span>
                        <span
                          className={
                            aprieta
                              ? "riel__paso riel__paso--aprieta"
                              : "riel__paso"
                          }
                        >
                          {pasoDelRiel(meso, numero)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>

              <Semana
                meso={meso}
                numero={semanaAbierta}
                sesiones={mias
                  .filter((s) => s.week_number === semanaAbierta)
                  .sort((a, b) => a.day_number - b.day_number)}
                abierta={abierta}
                onAbrir={setAbierta}
                semanasArmadas={[...new Set(mias.map((s) => s.week_number))]}
              />
            </div>
          );
        }}
      </Consulta>
      <Aviso de={duplicar} />
      <Aviso de={pegarBloque} />
    </section>
  );
}

/**
 * La rutina del atleta: sus bloques, sus semanas y lo que hay en cada día.
 *
 * Dejó de ser una pantalla propia. Vive como una pestaña del panel del atleta,
 * al lado de las gráficas, porque son la misma conversación: se arma un bloque,
 * se mira si se está cumpliendo, se corrige. Tenerlas en dos direcciones
 * distintas obligaba a ir y volver para hacer una sola cosa.
 */
export function Rutina({ atletaId }: { atletaId: string }) {
  const programas = useProgramas(atletaId);
  const [programa, setPrograma] = useState<string | undefined>();
  // Qué bloque está en el portapapeles. Vive acá porque copiar y pegar son dos
  // bloques distintos del mismo programa.
  const [bloqueCopiado, setBloqueCopiado] = useState<string | null>(null);
  // Qué bloque está proyectando la barra lateral. Uno solo, y de la pantalla y
  // no de cada bloque: la proyección es la columna de la derecha, y dos abiertas
  // a la vez serían dos futuros distintos compitiendo por el mismo lugar.
  const [proyectando, setProyectando] = useState<string | null>(null);
  const mesociclos = useMesociclos(programa);

  if (programas.isPending) return <Cargando que="los programas" />;
  if (programas.isError) return <Falla que="los programas" />;

  const elegido: Programa | undefined =
    programas.data.find((p) => p.id === programa) ?? programas.data[0];
  if (elegido && elegido.id !== programa) setPrograma(elegido.id);

  return (
    <>
      <NuevoPrograma atletaId={atletaId} />
      {programas.data.length > 1 ? (
        <label>
          Programa{" "}
          <select
            value={programa ?? ""}
            onChange={(e) => setPrograma(e.target.value)}
          >
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
              motivo:
                "Este programa no tiene bloques todavía. Creá el primero acá arriba.",
            }}
          >
            {(lista) => {
              const proyectado = lista.find((m) => m.id === proyectando);
              return (
                <div
                  className={`editor${proyectado ? " editor--con-lateral" : ""}`}
                >
                  <div className="editor__contenido">
                    {lista.map((meso) => (
                      <Bloque
                        key={meso.id}
                        meso={meso}
                        atletaId={atletaId}
                        cuantos={lista.length}
                        copiado={bloqueCopiado}
                        onCopiar={setBloqueCopiado}
                        proyectando={proyectando}
                        onProyectar={setProyectando}
                      />
                    ))}
                  </div>
                  {/* Fuera de la tarjeta del bloque a propósito: es una columna
                      de la pantalla, no una parte de un mesociclo. Adentro
                      competía por el ancho justo con las semanas, que es lo que
                      hay que mirar mientras se lee. */}
                  {proyectado ? (
                    <aside
                      className="editor__lateral"
                      aria-label={`Proyección de ${proyectado.label}`}
                    >
                      <PanelDeProyeccion
                        meso={proyectado}
                        onCerrar={() => setProyectando(null)}
                      />
                    </aside>
                  ) : null}
                </div>
              );
            }}
          </Consulta>
        </>
      ) : (
        <p>Este atleta no tiene programas. Creá el primero.</p>
      )}
    </>
  );
}

export { Catalogo };
