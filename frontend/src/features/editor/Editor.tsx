import { useState } from "react";

import { ErrorDelApi } from "../../api/cliente";
import {
  useEjercicios,
  useEscrituraDelEditor,
  useMesociclos,
  usePatrones,
  useProgramas,
  useSesion,
  type Ejercicio,
  type Mesociclo,
  type Patron,
  type Programa,
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
    "Semana duplicada",
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
        <input inputMode="numeric" value={reps} onChange={(e) => setReps(e.target.value)} />
      </label>
      <label className="campo">
        <span>RIR</span>
        <input inputMode="decimal" value={rir} onChange={(e) => setRir(e.target.value)} />
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
      <small className="serie-nueva__nota">Sin kg, el peso lo elige el atleta.</small>
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

  const agregar = useEscrituraDelEditor<unknown, void>((enviar) =>
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
  const borrarSerie = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/prescribed-sets/${id}`),
    "Serie borrada",
  );
  const borrarEjercicio = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/prescriptions/${id}`),
    "Ejercicio sacado del día",
  );
  const duplicarEjercicio = useEscrituraDelEditor<unknown, string>((enviar, _, id) =>
    enviar(`/api/prescriptions/${id}/duplicate`),
    "Ejercicio duplicado",
  );
  const reordenar = useEscrituraDelEditor<unknown, string[]>((_, mutar, ids) =>
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
                elementos={datos.blocks.map((b) => ({ ...b, id: b.prescription_id }))}
                onOrdenar={(ids) => reordenar.mutate(ids)}
                deshabilitado={reordenar.isPending}
              >
                {(bloque) => (
                  <>
                    <div className="ejercicio__cabecera">
                      <strong className="ejercicio__nombre">{bloque.exercise}</strong>
                      <span className="chip">{bloque.pattern}</span>
                      <span className="empuja" />
                      {/* Calladas y a la derecha: el nombre del ejercicio es lo
                          que se lee, y dos botones con peso al lado se lo
                          comen. */}
                      <button
                        type="button"
                        className="sutil"
                        onClick={() => duplicarEjercicio.mutate(bloque.prescription_id)}
                      >
                        Duplicar
                      </button>
                      <button
                        type="button"
                        className="sutil ejercicio__borrar"
                        onClick={() => borrarEjercicio.mutate(bloque.prescription_id)}
                        aria-label={`Sacar ${bloque.exercise} de este día`}
                        title="Sacar de este día"
                      >
                        <Tacho />
                      </button>
                    </div>
                    <ul className="lista">
                      {bloque.sets.map((serie) => (
                        <li key={serie.id} className="serie">
                          <span className="serie__numero">{serie.set_number}</span>
                          <span className="serie__dato">
                            <strong>
                              {serie.reps_min ?? "?"}
                              {serie.reps_max && serie.reps_max !== serie.reps_min
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
                .filter((ej) => !patronFiltro || ej.pattern_code === patronFiltro)
                .map((ej) => (
                  <option key={ej.id} value={ej.id}>
                    {ej.name}
                  </option>
                ))}
            </select>
            {/* Las etiquetas arriba y visibles, no en el `placeholder`: un
                `placeholder` desaparece al escribir y quedan cuatro cajas de
                números iguales sin saber cuál era el RIR. */}
            <Selector etiqueta="Series" valor={series} onCambio={setSeries} max={8} />
            <label className="campo">
              <span>Reps</span>
              <input inputMode="numeric" value={reps} onChange={(e) => setReps(e.target.value)} />
            </label>
            <label className="campo">
              <span>RIR</span>
              <input inputMode="decimal" value={rir} onChange={(e) => setRir(e.target.value)} />
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
            <button type="submit" className="principal" disabled={!elegido || agregar.isPending}>
              Agregar ejercicio
            </button>
            <small className="serie-nueva__nota">
              Se crean {series} series iguales. Sin kg, el peso lo elige el atleta.
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
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
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
      <small>El patrón es obligatorio: sin él no hay análisis de volumen.</small>
      <Aviso de={crear} />
    </section>
  );
}

function AgregarPatron() {
  const [nombre, setNombre] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
    enviar("/api/movement-patterns", { label_es: nombre.trim() }),
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

function FilaDeEjercicio({ ej, nombreDe }: { ej: Ejercicio; nombreDe: (c: string) => string }) {
  const patrones = usePatrones();
  const [editando, setEditando] = useState(false);
  const [nombre, setNombre] = useState(ej.name);
  const [patron, setPatron] = useState(ej.pattern_code);

  const guardar = useEscrituraDelEditor<unknown, void>((_, mutar) =>
    mutar("PATCH", `/api/exercises/${ej.id}`, { name: nombre.trim(), pattern_code: patron }),
    "Ejercicio guardado",
  );
  const [confirmando, setConfirmando] = useState(false);
  const borrar = useEscrituraDelEditor<unknown, void>((_, mutar) =>
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
          <button type="submit" className="principal" disabled={guardar.isPending}>
            Guardar
          </button>
          <button type="button" className="sutil" onClick={() => setEditando(false)}>
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
                  {ej.prescription_count === 1 ? "día" : "días"} y se va a sacar de todos.{" "}
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
  const borrar = useEscrituraDelEditor<unknown, void>((_, mutar) =>
    mutar("DELETE", `/api/movement-patterns/${patron.code}`),
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

  const coincide = (texto: string) => plano(texto).includes(plano(busqueda.trim()));
  const ejercisFiltrados = (ejercicios.data ?? []).filter((e) => coincide(e.name));
  const patronesFiltrados = (patrones.data ?? []).filter((p) => coincide(p.label_es));

  const verEjercicios = filtro !== "patrones";
  const verPatrones = filtro !== "ejercicios";
  const vacio =
    (verEjercicios ? ejercisFiltrados.length : 0) + (verPatrones ? patronesFiltrados.length : 0) ===
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
              patronesFiltrados.map((p) => <FilaDePatron key={p.code} patron={p} />)}
          </ul>
        )}
      </section>
    </>
  );
}

// --- La pantalla ----------------------------------------------------------------

function NuevoPrograma({ atletaId }: { atletaId: string }) {
  const [nombre, setNombre] = useState("");
  const crear = useEscrituraDelEditor<unknown, void>((enviar) =>
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
  // La semana que se está editando ocupa el ancho entero. Media pantalla alcanza
  // para leer qué días tiene, y no para armar un ejercicio con sus series: ahí
  // todo se parte en tres renglones y deja de entenderse.
  const editando = sesiones.some((s) => s.id === abierta);
  const usados = new Set(sesiones.map((s) => s.day_number));
  const siguiente = [1, 2, 3, 4, 5, 6, 7].find((d) => !usados.has(d));

  const agregar = useEscrituraDelEditor<unknown, number>((enviar, _, dia) =>
    enviar(`/api/mesocycles/${meso.id}/sessions`, { week_number: numero, day_number: dia }),
    "Día agregado",
  );
  const borrar = useEscrituraDelEditor<unknown, string>((_, mutar, id) =>
    mutar("DELETE", `/api/sessions/${id}`),
    "Día borrado",
  );

  return (
    <section className={`semana${editando ? " semana--editando" : ""}`}>
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
}

export { Catalogo };
