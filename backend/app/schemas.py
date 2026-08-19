from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AthleteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    level: str | None = None
    #: Viaja porque la interfaz tiene que ofrecer acciones distintas según el
    #: estado, y derivarlo de que la ficha aparezca o no en el listado dejaría a
    #: un vínculo pausado sin forma de reanudarse: invisible y sin botón.
    estado: str = "activo"

    #: Cuándo entrenó por última vez. Es el dato por el que existe este listado:
    #: le dice al entrenador quién se está cayendo, que es lo que una planilla no
    #: puede contestar sola. `None` cuando todavía no registró nada.
    ultima_sesion: datetime | None = None
    #: El programa vigente, si hay uno. Sirve para reconocer la ficha sin abrirla.
    programa_actual: str | None = None
    #: En qué semana del bloque actual está, y de cuántas.
    #:
    #: Del **mesociclo** y no del programa entero, porque `program` no declara
    #: ninguna duración: sumar los `week_count` de sus bloques da un denominador
    #: que se mueve cada vez que el entrenador agrega uno, y una barra cuyo total
    #: cambia no es una barra de progreso. El mesociclo además es la unidad que
    #: declara su propia progresión, así que «semana 3 de 4» es accionable.
    semana_actual: int | None = None
    semanas_del_bloque: int | None = None


class AthleteIn(BaseModel):
    """What the coach types when the person does not exist as an identity yet.

    No `coach_id` and no `user_id`, on purpose. The space is the caller's own —
    taking it from the body would let somebody file an athlete into another
    coach's space, and `user_id` is filled in when the person claims the record
    through an invitation, not something the coach asserts.
    """

    full_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=160)
    birth_date: date | None = None
    bodyweight_kg: float | None = Field(default=None, gt=0, le=400)
    level: Literal["principiante", "intermedio", "avanzado"] | None = None
    goal: str | None = None
    notes: str | None = None


class AthleteCreated(BaseModel):
    """The record as it exists the moment it is created.

    `has_account` rather than the raw `user_id`: what the coach needs to know is
    whether this person can log in yet, and exposing the identity key would leak
    which records belong to the same person across coaches.
    """

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    level: str | None = None
    has_account: bool


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    set_number: int
    reps_min: int | None = None
    reps_max: int | None = None
    rir_min: float | None = None
    rir_max: float | None = None
    target_load_kg: float | None = None
    reps_done: int | None = None
    load_done_kg: float | None = None
    rir_done: float | None = None


class ExerciseBlock(BaseModel):
    prescription_id: uuid.UUID
    exercise: str
    pattern: str
    rest_seconds: int | None = None
    coach_note: str | None = None
    sets: list[SetOut]


class SessionSummary(BaseModel):
    """One listing row: enough to pick a session, without loading its sets.

    `week_number` is relative to the mesocycle and `mesocycle_ordinal` is
    relative to the program (`UniqueConstraint("program_id", "ordinal")`). So
    neither the week alone nor the (ordinal, week) pair identifies a session:
    the full four-part key including `program_id` is needed — which is exactly
    the argument for fetching the detail by `id` instead of rebuilding the key
    on the client.

    An athlete with one finished program and one active program has two
    mesocycles numbered `ordinal=1`. That is not an edge case, it is the norm
    from the second mesocycle onwards.
    """

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    program_id: uuid.UUID
    program: str
    #: El id del bloque, y no sólo su nombre.
    #:
    #: Sin esto la interfaz sólo puede agrupar por `mesocycle`, que es una
    #: etiqueta que el entrenador escribe y puede repetir — y esta agenda trae
    #: las sesiones de **todos** los programas del atleta. Dos bloques llamados
    #: «Acumulación» en programas distintos se mostraban las sesiones entre
    #: ellos: un bloque vacío parecía lleno.
    mesocycle_id: uuid.UUID
    mesocycle: str
    mesocycle_ordinal: int
    week_number: int
    day_number: int
    label: str | None = None
    scheduled_on: date | None = None

    #: Cuántas series pide este día y cuántas ya tienen respuesta.
    #:
    #: Sin esto, un día terminado y uno sin empezar se dibujan igual, y el atleta
    #: tiene que abrirlos para saber cuál le falta.
    #:
    #: «Con respuesta» y no «registradas»: una serie saltada también fue
    #: contestada — el atleta dijo que no la hizo. Contar sólo las registradas
    #: dejaría un día cerrado a propósito como si estuviera a medio hacer, para
    #: siempre.
    series_prescritas: int = 0
    series_respondidas: int = 0


class SessionOut(BaseModel):
    id: uuid.UUID
    mesocycle: str
    mesocycle_ordinal: int
    week_number: int
    day_number: int
    blocks: list[ExerciseBlock]


class LogSetIn(BaseModel):
    reps: int | None = Field(default=None, ge=0, le=200)
    load_kg: float | None = Field(default=None, ge=0, le=1000)
    rir: float | None = Field(default=None, ge=0, le=10)
    was_skipped: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _coherente(self) -> LogSetIn:
        if not self.was_skipped and self.reps is None:
            raise ValueError("una serie no saltada necesita reps")
        return self


class LogSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reps: int | None
    load_kg: float | None
    rir: float | None
    e1rm_kg: float | None
    performed_at: datetime


class VolumeOut(BaseModel):
    week: int
    pattern: str
    sets_planned: int
    sets_done: int
    tonnage_kg: float


class AceptarInvitacionIn(BaseModel):
    token: str = Field(min_length=1)


class InvitacionAceptada(BaseModel):
    resultado: Literal["aceptada"]


class CambioDeEstadoIn(BaseModel):
    """Qué se le pide al vínculo. Los valores son los de `vinculo.Accion`."""

    accion: Literal["pausar", "reanudar", "archivar", "reactivar"]


class EstadoOut(BaseModel):
    athlete_id: uuid.UUID
    estado: str


class InvitacionCreada(BaseModel):
    """El token en claro viaja acá y en ningún otro lado.

    No hay ruta que lo vuelva a mostrar, y la tabla guarda su hash. Si se pierde,
    se genera uno nuevo — que además invalida éste, que es lo que se quiere.
    """

    token: str
    expires_at: datetime


class PatternAdherenceOut(BaseModel):
    """Las tres preguntas de la adherencia, por patrón de movimiento.

    Viaja con `sets_planned` y no sólo con los porcentajes: un porcentaje sin su
    denominador miente. Cero de una serie y cero de doscientas se dibujan igual y
    significan cosas opuestas.
    """

    pattern: str
    sets_planned: int
    sets_done: int
    completion_rate: float
    in_range_rate: float
    avg_rir_deviation: float | None


class LoadPointOut(BaseModel):
    """One week of an exercise. `load_kg` is null when nothing was logged.

    A list and not an object keyed by week: JSON object keys are strings, and a
    chart that has to parse "3" back into a number to sort by it will sort "10"
    before "2" the first time somebody forgets.
    """

    week: int
    load_kg: float | None


class LoadProgressionOut(BaseModel):
    exercise: str
    points: list[LoadPointOut]


class AdherenceOut(BaseModel):
    week: int
    sets_planned: int
    sets_done: int
    completion_rate: float
    in_range_rate: float
    tonnage_kg: float
    avg_rir_deviation: float | None


class CoachOut(BaseModel):
    """The coaching space, as it looks the moment it exists."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    display_name: str
    athlete_count: int


# --- El editor de rutinas -------------------------------------------------------
#
# La estructura que el entrenador arma: programa → mesociclo → sesión →
# prescripción → serie prescrita. Cada nivel tiene su alta y su modificación
# parcial, y la modificación parcial usa `None` como "no lo toques" en vez de
# como "ponelo en nulo". Distinguir las dos cosas necesitaría un centinela, y el
# único campo donde borrar el valor es una operación real —la carga objetivo de
# una serie que pasa a ser autorregulada— se resuelve con su propio flag.


class ProgramIn(BaseModel):
    """A programme belongs to an athlete of the caller's; the space is not in the body."""

    name: str = Field(min_length=1, max_length=120)
    starts_on: date | None = None


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    athlete_id: uuid.UUID
    name: str
    starts_on: date | None = None
    status: str | None = None


class MesocycleIn(BaseModel):
    ordinal: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=120)
    week_count: int = Field(ge=1, le=16)
    focus: str | None = Field(default=None, max_length=120)
    rir_progression: list[int] | None = Field(default=None, max_length=52)


class MesocyclePatch(BaseModel):
    ordinal: int | None = Field(default=None, ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    week_count: int | None = Field(default=None, ge=1, le=16)
    focus: str | None = Field(default=None, max_length=120)
    rir_progression: list[int] | None = Field(default=None, max_length=52)


class MesocycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    program_id: uuid.UUID
    ordinal: int
    label: str
    week_count: int
    focus: str | None = None
    rir_progression: list[int] | None = None


class SessionIn(BaseModel):
    """A session is a slot: which week of the block, and which day of that week."""

    week_number: int = Field(ge=1)
    day_number: int = Field(ge=1, le=7)
    label: str | None = Field(default=None, max_length=120)
    scheduled_on: date | None = None


class SessionPatch(BaseModel):
    week_number: int | None = Field(default=None, ge=1)
    day_number: int | None = Field(default=None, ge=1, le=7)
    label: str | None = Field(default=None, max_length=120)
    scheduled_on: date | None = None


class SessionCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    mesocycle_id: uuid.UUID
    week_number: int
    day_number: int
    label: str | None = None
    scheduled_on: date | None = None


class PrescriptionIn(BaseModel):
    exercise_id: uuid.UUID
    position: int | None = Field(default=None, ge=1)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    coach_note: str | None = Field(default=None, max_length=500)
    superset_key: str | None = Field(default=None, max_length=8)
    # Las series del alta, en la misma transacción que la prescripción.
    #
    # Medido sobre la programación real: 473 de 473 ejercicios prescriptos
    # tienen todas sus series idénticas. Crear el ejercicio vacío y después
    # agregar de a una obligaba a repetir el mismo dato tres veces, y dejaba
    # una ventana donde el ejercicio existe sin nada prescripto — si la segunda
    # llamada falla, el atleta ve un ejercicio sin series.
    #
    # Es una lista y no "cantidad + esquema" a propósito: que sean todas
    # iguales es un hecho de estos datos, no una regla. El día que una difiera,
    # la API ya la acepta y no hay que cambiarla.
    sets: list[PrescribedSetIn] = Field(default_factory=list, max_length=20)


class PrescriptionPatch(BaseModel):
    position: int | None = Field(default=None, ge=1)
    rest_seconds: int | None = Field(default=None, ge=0, le=3600)
    coach_note: str | None = Field(default=None, max_length=500)
    superset_key: str | None = Field(default=None, max_length=8)


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID
    exercise_id: uuid.UUID
    position: int
    rest_seconds: int | None = None
    coach_note: str | None = None
    superset_key: str | None = None


class _Intensidad(BaseModel):
    """Las tres formas de prescribir, y lo que ninguna puede violar.

    Carga absoluta, carga relativa al máximo, o autorregulada —sólo RIR, el peso
    lo elige el atleta ese día—. Las tres conviven y el entrenador usa las tres,
    pero una serie no puede ser absoluta y relativa a la vez.

    Los campos viven acá y no repetidos en el alta y la modificación: son la
    misma intensidad, y una copia es un lugar donde los límites se desincronizan.

    La base ya impide la ambigüedad con un CHECK. Esto la rechaza antes, y el
    motivo no es desconfiar de la base: un CHECK violado sube como un error de
    integridad sin nombre de campo, y quien lo recibe no sabe cuál de los dos
    sacar.
    """

    reps_min: int | None = Field(default=None, ge=0, le=200)
    reps_max: int | None = Field(default=None, ge=0, le=200)
    rir_min: float | None = Field(default=None, ge=0, le=10)
    rir_max: float | None = Field(default=None, ge=0, le=10)
    target_load_kg: float | None = Field(default=None, ge=0, le=1000)
    target_pct_1rm: float | None = Field(default=None, gt=0, le=1.5)
    tempo: str | None = Field(default=None, max_length=16)
    set_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _una_sola_forma_de_carga(self) -> _Intensidad:
        if self.target_load_kg is not None and self.target_pct_1rm is not None:
            raise ValueError(
                "una serie es de carga absoluta o relativa, no las dos: "
                "mandá target_load_kg o target_pct_1rm, no ambos"
            )
        return self

    @model_validator(mode="after")
    def _los_rangos_no_estan_al_reves(self) -> _Intensidad:
        for menor, mayor, nombre in (
            (self.reps_min, self.reps_max, "repeticiones"),
            (self.rir_min, self.rir_max, "RIR"),
        ):
            if menor is not None and mayor is not None and mayor < menor:
                raise ValueError(f"el rango de {nombre} está al revés: el máximo es menor")
        return self


class PrescribedSetIn(_Intensidad):
    is_amrap: bool = False


class PrescribedSetPatch(_Intensidad):
    """La carga se borra con `autorregulada`, no mandando `None`.

    En una modificación parcial `None` significa "no lo toques", así que sin este
    flag no habría forma de decir "sacale el peso, que lo elija el atleta": el
    campo ausente y el campo en nulo se ven iguales.
    """

    is_amrap: bool | None = None
    autorregulada: bool = False


class PrescribedSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    prescription_id: uuid.UUID
    set_number: int
    reps_min: int | None = None
    reps_max: int | None = None
    rir_min: float | None = None
    rir_max: float | None = None
    target_load_kg: float | None = None
    target_pct_1rm: float | None = None
    tempo: str | None = None
    is_amrap: bool = False


class OrderIn(BaseModel):
    """El orden completo y no un movimiento suelto.

    Mandar la lista entera hace la operación idempotente y deja que el servidor
    valide que están todos: un "movete a la posición 3" obliga al cliente a saber
    qué había en 3, y dos pestañas abiertas lo saben distinto.
    """

    ids: list[uuid.UUID] = Field(min_length=1)


class ExerciseIn(BaseModel):
    """El patrón de movimiento es obligatorio, y no es burocracia.

    Sin patrón no hay análisis de volumen, que es la razón de ser del producto.
    En la planilla original era opcional y 354 de 1.326 series quedaron sin
    clasificar.
    """

    name: str = Field(min_length=1, max_length=120)
    pattern_code: str = Field(min_length=1, max_length=64)
    is_competition_lift: bool = False
    video_url: str | None = Field(default=None, max_length=500)
    cues: str | None = Field(default=None, max_length=500)


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    pattern_code: str
    is_competition_lift: bool
    #: `None` es el catálogo global, disponible para todos los entrenadores.
    coach_id: uuid.UUID | None = None
    video_url: str | None = None
    cues: str | None = None
    #: En cuántas prescripciones está. Viaja para que la confirmación de borrado
    #: pueda decir qué se lleva puesto en vez de preguntar a ciegas: «esto no se
    #: puede deshacer» sin un número no ayuda a decidir.
    prescription_count: int = 0


class PatternOut(BaseModel):
    """Los patrones que el entrenador puede elegir: la base común más los suyos.

    Son un catálogo y no texto libre, que es lo que hace contestable la pregunta
    por volumen por patrón. Dejó de ser cerrado —cada entrenador amplía el suyo—
    pero sigue siendo un conjunto de valores y no una descripción escrita a mano
    en cada ejercicio, que es lo que importaba.

    `coach_id` viaja para que la pantalla sepa cuál puede borrar: la base común se
    lee, y ofrecer el botón sobre ella sería prometer algo que el servidor
    rechaza.
    """

    model_config = ConfigDict(from_attributes=True)
    code: str
    label_es: str
    is_compound: bool | None = None
    coach_id: uuid.UUID | None = None


class DuplicarMesocicloIn(BaseModel):
    """A dónde va la copia del bloque.

    `None` crea uno nuevo al final del programa; un id lo copia dentro de ese,
    que tiene que estar vacío. Es la misma operación con distinto destino, y por
    eso comparten ruta.
    """

    to_mesocycle: uuid.UUID | None = None


class DuplicarSemanaIn(BaseModel):
    """De qué semana a qué semana, las dos en el cuerpo.

    La de origen no viaja en la ruta aunque sea lo primero que uno escribiría: los
    parámetros de ruta de esta API son identificadores de recurso, y una semana es
    un número dentro de un mesociclo. El recorrido que prueba "un recurso ajeno
    contesta igual que uno inexistente" llena cada parámetro con un identificador
    inventado, y un entero ahí devuelve 422 antes de mirar de quién es el
    mesociclo — o sea que la ruta quedaría sin esa cobertura.
    """

    from_week: int = Field(ge=1)
    to_week: int = Field(ge=1)


class DuplicarSesionIn(BaseModel):
    to_week: int = Field(ge=1)
    to_day: int = Field(ge=1, le=7)


class ExercisePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    pattern_code: str | None = Field(default=None, min_length=1, max_length=64)
    is_competition_lift: bool | None = None
    video_url: str | None = Field(default=None, max_length=500)
    cues: str | None = Field(default=None, max_length=500)


class PatternIn(BaseModel):
    """Un patrón nuevo. El código se deriva del nombre, no se pide.

    Pedirlo sería pedir dos veces lo mismo y dejar que se contradigan: un
    «Antebrazo» con código `bíceps` es un dato roto que nadie mira hasta que el
    análisis de volumen sale mal.
    """

    label_es: str = Field(min_length=1, max_length=80)
    is_compound: bool = False
