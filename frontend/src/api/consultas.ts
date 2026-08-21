import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAvisar } from "../components/Avisos";
import { useRol } from "../lib/Rol";
import { useApi, useEnviar, useMutar } from "./useApi";

export type Atleta = {
  id: string;
  full_name: string;
  level: string | null;
  estado?: string;
  /** Cuándo entrenó por última vez. `null` si todavía no registró nada — que no
   *  es lo mismo que hace mucho, y por eso no viaja como una fecha vieja. */
  ultima_sesion?: string | null;
  programa_actual?: string | null;
  /** En qué semana del bloque actual está, y de cuántas. */
  semana_actual?: number | null;
  semanas_del_bloque?: number | null;
};

/**
 * The coach's athletes.
 *
 * No filtering happens here, and that is the decision: which athletes a coach
 * sees is decided by the database — row level security for whose they are, and
 * the endpoint's own predicate for which states count as current. Repeating
 * either rule in the browser creates a second copy that drifts, and the copy
 * that drifts is always the one nobody remembers writing.
 */
export function useAtletas(forzado?: "coach" | "athlete") {
  const { rol: activo } = useRol();
  // El rol **efectivo**, no el parámetro. La primera versión de esto miraba el
  // argumento: llamada sin él, la clave quedaba `["atletas", undefined]` para los
  // dos roles y TanStack Query servía al atleta la respuesta cacheada del
  // entrenador. Cambiar de rol no cambiaba nada de lo que se veía.
  const rol = forzado ?? activo;
  const pedir = useApi(rol);
  // El entrenador pide también los cerrados: un vínculo pausado que no aparece
  // en ninguna lista queda sin forma de reanudarse. El atleta pide los suyos, y
  // los suyos son los que son.
  const ruta = rol === "athlete" ? "/api/athletes" : "/api/athletes?incluir_cerrados=true";
  return useQuery({
    // El rol es parte de la identidad de la consulta y no un detalle de cómo se
    // pide: la misma ruta contesta cosas distintas según quién pregunte.
    queryKey: ["atletas", rol],
    queryFn: ({ signal }) => pedir(ruta, signal) as Promise<Atleta[]>,
  });
}

export type AdherenciaDePatron = {
  pattern: string;
  sets_planned: number;
  sets_done: number;
  completion_rate: number;
  in_range_rate: number;
  avg_rir_deviation: number | null;
};

/**
 * Adherence by movement pattern, already sorted worst-first by the API.
 *
 * The order is not re-derived here on purpose. It is part of the answer — it puts
 * the pattern being skipped at the top without anybody looking for it — and a
 * second sort in the browser is a second place for it to change.
 */
export function useAdherenciaPorPatron(atletaId: string) {
  const pedir = useApi();
  return useQuery({
    queryKey: ["adherencia", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/adherence/by-pattern`, signal) as Promise<
        AdherenciaDePatron[]
      >,
  });
}

export type VolumenSemanal = {
  week: number;
  pattern: string;
  sets_planned: number;
  sets_done: number;
  tonnage_kg: number;
};

export function useVolumen(atletaId: string) {
  const pedir = useApi();
  return useQuery({
    queryKey: ["volumen", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/volume`, signal) as Promise<VolumenSemanal[]>,
  });
}

export type PuntoDeCarga = { week: number; load_kg: number | null };
export type ProgresionDeEjercicio = { exercise: string; points: PuntoDeCarga[] };

export function useProgresion(atletaId: string) {
  const pedir = useApi();
  return useQuery({
    queryKey: ["progresion", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/progression`, signal) as Promise<ProgresionDeEjercicio[]>,
  });
}

export type InvitacionCreada = { token: string; expires_at: string };

/**
 * The coach issues a link for a record that has no account yet.
 *
 * The clear token comes back here and nowhere else — the table keeps its hash,
 * and no route can show it again. So the caller has exactly one chance to put it
 * in front of somebody, which is why this is a mutation whose result the screen
 * holds rather than a query that could be refetched into nothing.
 *
 * Issuing invalidates whatever was pending for that record. That is not this
 * code's doing: a partial unique index admits one usable invitation per athlete,
 * so the server revokes before inserting or the insert does not commit.
 */
export function useGenerarInvitacion() {
  const enviar = useEnviar();
  return useMutation({
    mutationFn: (atletaId: string) =>
      enviar(`/api/athletes/${atletaId}/invitation`) as Promise<InvitacionCreada>,
  });
}

/**
 * The athlete claims the record the coach already built.
 *
 * No role is sent, and that is forced rather than chosen: whoever accepts is not
 * yet an athlete of anybody, so there is no active role to assert. The endpoint
 * reads no `Active-Role` for the same reason.
 */
export function useAceptarInvitacion() {
  const enviar = useEnviar(null);
  return useMutation({
    mutationFn: (token: string) =>
      enviar("/api/me/invitation", { token }) as Promise<{ resultado: "aceptada" }>,
  });
}

// --- El espacio del entrenador --------------------------------------------------

export type Coach = { id: string; display_name: string; athlete_count: number };

/**
 * El alta de entrenador, que es el agujero que hacía que entrar por primera vez
 * terminara en 403 y punto muerto.
 */
export function useCrearCoach() {
  const enviar = useEnviar(null);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => enviar("/api/me/coach") as Promise<Coach>,
    // Todo lo que estaba en 403 pasa a poder resolverse. Sin esto la pantalla
    // muestra "ya sos entrenador" con el listado todavía en su error viejo.
    onSuccess: () => qc.invalidateQueries(),
  });
}

export function useCrearAtleta() {
  const enviar = useEnviar();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (datos: { full_name: string; email?: string; level?: string }) =>
      enviar("/api/athletes", datos) as Promise<Atleta>,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["atletas"] }),
  });
}

export type Accion = "pausar" | "reanudar" | "archivar" | "reactivar";

export function useCambiarEstado(atletaId: string) {
  const enviar = useEnviar();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (accion: Accion) =>
      enviar(`/api/athletes/${atletaId}/estado`, { accion }) as Promise<{ estado: string }>,
    onSuccess: () => qc.invalidateQueries(),
  });
}

// --- El editor de rutinas -------------------------------------------------------

export type Programa = { id: string; name: string; starts_on: string | null };
export type Mesociclo = {
  id: string;
  ordinal: number;
  label: string;
  week_count: number;
  focus: string | null;
  rir_progression: number[] | null;
};
export type Sesion = {
  id: string;
  week_number: number;
  day_number: number;
  label: string | null;
};
export type Prescripcion = {
  id: string;
  exercise_id: string;
  position: number;
  rest_seconds: number | null;
  coach_note: string | null;
};
export type SeriePrescrita = {
  id: string;
  set_number: number;
  reps_min: number | null;
  reps_max: number | null;
  rir_min: number | null;
  rir_max: number | null;
  target_load_kg: number | null;
  target_pct_1rm: number | null;
};
export type Ejercicio = {
  id: string;
  name: string;
  pattern_code: string;
  coach_id: string | null;
  /** En cuántos días está. Lo necesita la confirmación de borrado, antes de preguntar. */
  prescription_count: number;
};
export type Patron = {
  code: string;
  label_es: string;
  is_compound?: boolean;
  coach_id?: string | null;
};

export function useProgramas(atletaId: string) {
  const pedir = useApi("coach");
  return useQuery({
    queryKey: ["programas", atletaId],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/programs`, signal) as Promise<Programa[]>,
  });
}

export function useMesociclos(programaId: string | undefined) {
  const pedir = useApi("coach");
  return useQuery({
    queryKey: ["mesociclos", programaId],
    enabled: Boolean(programaId),
    queryFn: ({ signal }) =>
      pedir(`/api/programs/${programaId}/mesocycles`, signal) as Promise<Mesociclo[]>,
  });
}

/**
 * Lo que la progresión declarada va a producir, antes de duplicar nada.
 *
 * Lo calcula el servidor con las mismas funciones que corre al copiar. Rehacer
 * la cuenta acá sería más rápido de escribir y quedaría vieja sin avisar: un
 * panel que predice algo distinto de lo que hace el botón de al lado es peor
 * que no tener panel.
 */
export type SerieProyectada = {
  set_number: number;
  reps_min: number | null;
  reps_max: number | null;
  rir_min: number | null;
  rir_max: number | null;
  target_load_kg: number | null;
  target_pct_1rm: number | null;
  is_amrap: boolean;
};

export type EjercicioProyectado = {
  exercise_name: string;
  position: number;
  superset_key: string | null;
  sets: SerieProyectada[];
};

export type DiaProyectado = {
  day_number: number;
  label: string | null;
  ejercicios: EjercicioProyectado[];
};

/** `aprieta` es menos RIR, o sea más duro; `afloja` es la descarga. */
export type Movimiento = "base" | "sostiene" | "aprieta" | "afloja";

export type SemanaProyectada = {
  week_number: number;
  rir_delta: number;
  movimiento: Movimiento;
  ya_armada: boolean;
  dias: DiaProyectado[];
};

export type Proyeccion = {
  semana_base: number | null;
  declara_progresion: boolean;
  semanas: SemanaProyectada[];
};

export function useProyeccion(mesocicloId: string, habilitada: boolean) {
  const pedir = useApi("coach");
  return useQuery({
    queryKey: ["proyeccion", mesocicloId],
    // Sólo cuando alguien la abre. Sin esto cada bloque de la pantalla la pide
    // al montarse, y son tantas consultas como bloques tenga el programa para
    // dibujar algo que nadie está mirando.
    enabled: habilitada,
    queryFn: ({ signal }) =>
      pedir(`/api/mesocycles/${mesocicloId}/projection`, signal) as Promise<Proyeccion>,
  });
}

export function useEjercicios() {
  const pedir = useApi("coach");
  return useQuery({
    queryKey: ["ejercicios"],
    queryFn: ({ signal }) => pedir("/api/exercises", signal) as Promise<Ejercicio[]>,
  });
}

export function usePatrones() {
  const pedir = useApi("coach");
  return useQuery({
    queryKey: ["patrones"],
    // Once filas que no cambian nunca: no tiene sentido volver a pedirlas.
    staleTime: Infinity,
    queryFn: ({ signal }) => pedir("/api/movement-patterns", signal) as Promise<Patron[]>,
  });
}

/** Una sola fábrica para todas las escrituras del editor, que son quince variantes
 *  del mismo gesto: mandar algo y volver a pedir lo que quedó. */
export function useEscrituraDelEditor<T, V>(
  hacer: (
    enviar: (ruta: string, cuerpo?: unknown) => Promise<unknown>,
    mutar: (metodo: "PUT" | "PATCH" | "DELETE", ruta: string, cuerpo?: unknown) => Promise<unknown>,
    variables: V,
  ) => Promise<T>,
  /**
   * Qué decir cuando salió bien: «Serie agregada», «Semana duplicada».
   *
   * Se declara acá, al lado de la llamada, y no en el botón: hay acciones que
   * se disparan desde más de un lugar, y el aviso tiene que describir lo que
   * pasó en la base, no lo que decía el botón que se apretó.
   *
   * Opcional porque no toda escritura merece uno. Renombrar un ejercicio se ve
   * en el mismo campo que se acaba de editar, y avisarlo es ruido.
   */
  aviso?: string,
) {
  const enviar = useEnviar("coach");
  const mutar = useMutar("coach");
  const qc = useQueryClient();
  const avisar = useAvisar();
  return useMutation({
    mutationFn: (variables: V) => hacer(enviar, mutar, variables),
    // Invalida todo y no una clave puntual: el editor toca un árbol, y una
    // duplicación de semana cambia sesiones, prescripciones y series de una vez.
    // Afinar esto antes de que exista la pantalla sería adivinar.
    onSuccess: () => {
      qc.invalidateQueries();
      if (aviso) avisar(aviso);
    },
  });
}

// --- Lo que entrena el atleta ---------------------------------------------------

export type SesionDeLaAgenda = {
  id: string;
  /** El bloque al que pertenece. Agrupar por el nombre mezcla dos bloques que se
   *  llamen igual, y esta agenda trae los de todos los programas del atleta. */
  mesocycle_id: string;
  mesocycle: string;
  mesocycle_ordinal: number;
  week_number: number;
  day_number: number;
  /** Cuántas series pide el día y cuántas ya tienen respuesta — registrada o
   *  saltada. Un día terminado y uno sin empezar se dibujaban igual. */
  series_prescritas: number;
  series_respondidas: number;
};

export type SerieDelDia = {
  id: string;
  set_number: number;
  reps_min: number | null;
  reps_max: number | null;
  rir_min: number | null;
  rir_max: number | null;
  target_load_kg: number | null;
  reps_done: number | null;
  load_done_kg: number | null;
  rir_done: number | null;
};

export type BloqueDelDia = {
  prescription_id: string;
  exercise: string;
  pattern: string;
  rest_seconds: number | null;
  coach_note: string | null;
  sets: SerieDelDia[];
};

export type DetalleDeSesion = {
  id: string;
  mesocycle: string;
  week_number: number;
  day_number: number;
  blocks: BloqueDelDia[];
};

export function useAgenda(atletaId: string, rol?: "coach" | "athlete") {
  const pedir = useApi(rol);
  return useQuery({
    queryKey: ["agenda", atletaId, rol],
    queryFn: ({ signal }) =>
      pedir(`/api/athletes/${atletaId}/sessions`, signal) as Promise<SesionDeLaAgenda[]>,
  });
}

export function useSesion(sesionId: string, rol?: "coach" | "athlete") {
  const pedir = useApi(rol);
  return useQuery({
    queryKey: ["sesion", sesionId, rol],
    queryFn: ({ signal }) => pedir(`/api/sessions/${sesionId}`, signal) as Promise<DetalleDeSesion>,
  });
}

export type LoQueHizo = {
  reps?: number | null;
  load_kg?: number | null;
  rir?: number | null;
  was_skipped?: boolean;
  note?: string | null;
};

/**
 * El gesto central del producto: el atleta registra una serie.
 *
 * Va con rol `athlete` fijo y no con el del contexto. Registrar es del atleta —
 * la policy rechaza al entrenador— y dejar que el interruptor lo cambie sería
 * ofrecer un botón que contesta 409 según cómo quedó un `select` en otra
 * pantalla.
 */
export function useRegistrarSerie(sesionId: string) {
  const mutar = useMutar("athlete");
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ serieId, ...hizo }: LoQueHizo & { serieId: string }) =>
      mutar("PUT", `/api/sets/${serieId}/log`, hizo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sesion", sesionId] }),
  });
}
