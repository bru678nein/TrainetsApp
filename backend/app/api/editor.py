"""The routine editor: building the structure the athlete will train.

Programme → mesocycle → session → prescription → prescribed set. Every level can
be created, renamed, reordered and deleted, because a live programme gets
corrected: the athlete gets injured, the week went badly, the coach drops the
volume halfway through.

**Whose data it is is not checked here.** These handlers ask the database for a
row by id and answer 404 when there is none, which is also what happens when the
row belongs to somebody else — the policies filter it out before the query
returns. That is deliberate: someone else's identifier has to be
indistinguishable from one that does not exist, and an `if` comparing coach ids
would be a second copy of a rule the schema already holds.

**Being a coach is checked here**, once, on the router. An athlete's own policies
let them read their programme, and reading is all they should be able to do with
it.

Ordering is stored, not derived: `position` inside a session, `set_number` inside
a prescription, `ordinal` inside a programme. The four unique constraints that
protect those became deferrable in migration 0014, so a reorder is one statement
that shifts everything and settles at commit instead of a dance through
temporary values.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import TenantContext, require_tenant_context, solo_entrenador_al_dia
from app.models import (
    Exercise,
    Mesocycle,
    MovementPattern,
    PrescribedSet,
    Prescription,
    Program,
    Session,
)
from app.schemas import (
    DuplicarMesocicloIn,
    DuplicarSemanaIn,
    DuplicarSesionIn,
    ExerciseIn,
    ExerciseOut,
    ExercisePatch,
    MesocycleIn,
    MesocycleOut,
    MesocyclePatch,
    OrderIn,
    PatternIn,
    PatternOut,
    PrescribedSetIn,
    PrescribedSetOut,
    PrescribedSetPatch,
    PrescriptionIn,
    PrescriptionOut,
    PrescriptionPatch,
    ProgramIn,
    ProgramOut,
    SessionCreated,
    SessionIn,
    SessionPatch,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as OrmSession

editor = APIRouter(prefix="/api", dependencies=[Depends(require_tenant_context)])

T = TypeVar("T")


def _solo_entrenador(ctx: TenantContext) -> OrmSession:
    """The role check, in one place.

    The policies already stop an athlete from writing here, but they stop it with
    a row-level rejection that reads as "no permission" with no subject. Refusing
    up front says which rule was broken.
    """
    return solo_entrenador_al_dia(ctx, "sólo un entrenador edita rutinas")


def _o_404(db: OrmSession, modelo: type[T], id_: uuid.UUID, que: str) -> T:
    fila = db.get(modelo, id_)
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{que} inexistente")
    return fila


def _siguiente(
    db: OrmSession, columna: InstrumentedAttribute[int], filtro: ColumnElement[bool]
) -> int:
    """The next free slot in an ordered list, so creating does not need a number.

    The coach adds an exercise to the end far more often than to a precise
    position, and asking for the number every time means the client has to count
    what it already has on screen — and gets it wrong the moment two tabs are
    open.
    """
    usado = db.execute(select(func.max(columna)).where(filtro)).scalar()
    return (usado or 0) + 1


def _aplicar(fila: object, cambios: dict[str, object]) -> None:
    """`None` means "leave it alone", never "set it to null".

    A partial update that cannot tell those apart makes clearing a field
    impossible without a sentinel value. The one place clearing is a real
    operation — a set that stops having a target load because the athlete now
    picks the weight — has its own flag instead.
    """
    for campo, valor in cambios.items():
        if valor is not None:
            setattr(fila, campo, valor)


def _reordenar(db: OrmSession, filas: Sequence[Any], ids: list[uuid.UUID], columna: str) -> None:
    """Assigns 1..n in the order given, in one pass.

    The whole list arrives rather than a single move: it makes the operation
    idempotent and lets the server check nothing is missing. "Move this to
    position 3" needs the client to know what was at 3, and two open tabs know
    that differently.
    """
    por_id = {f.id: f for f in filas}
    if set(ids) != set(por_id) or len(ids) != len(por_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "el orden tiene que traer exactamente los mismos elementos que hay",
        )
    # Sin esto el desplazamiento pisa posiciones que todavía no se liberaron y el
    # único falla a mitad de camino, aunque el conjunto final sea válido.
    db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    for posicion, id_ in enumerate(ids, start=1):
        setattr(por_id[id_], columna, posicion)


# --- Programa -------------------------------------------------------------------


@editor.post(
    "/athletes/{athlete_id}/programs",
    response_model=ProgramOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_programa(
    athlete_id: uuid.UUID, payload: ProgramIn, ctx: TenantContext = Depends(require_tenant_context)
) -> Program:
    from app.models import Athlete

    db = _solo_entrenador(ctx)
    ficha = _o_404(db, Athlete, athlete_id, "atleta")
    programa = Program(
        coach_id=ficha.coach_id, athlete_id=ficha.id, name=payload.name, starts_on=payload.starts_on
    )
    db.add(programa)
    db.commit()
    return programa


@editor.get("/athletes/{athlete_id}/programs", response_model=list[ProgramOut])
def listar_programas(
    athlete_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> list[Program]:
    db = ctx.db
    return list(
        db.scalars(
            select(Program)
            .where(Program.athlete_id == athlete_id)
            .order_by(Program.starts_on, Program.id)
        ).all()
    )


# --- Mesociclo ------------------------------------------------------------------


@editor.post(
    "/programs/{program_id}/mesocycles",
    response_model=MesocycleOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_mesociclo(
    program_id: uuid.UUID,
    payload: MesocycleIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Mesocycle:
    db = _solo_entrenador(ctx)
    _o_404(db, Program, program_id, "programa")
    meso = Mesocycle(
        program_id=program_id,
        ordinal=payload.ordinal,
        label=payload.label,
        week_count=payload.week_count,
        focus=payload.focus,
        rir_progression=payload.rir_progression,
    )
    db.add(meso)
    db.commit()
    return meso


@editor.get("/programs/{program_id}/mesocycles", response_model=list[MesocycleOut])
def listar_mesociclos(
    program_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> list[Mesocycle]:
    return list(
        ctx.db.scalars(
            select(Mesocycle).where(Mesocycle.program_id == program_id).order_by(Mesocycle.ordinal)
        ).all()
    )


@editor.patch("/mesocycles/{mesocycle_id}", response_model=MesocycleOut)
def editar_mesociclo(
    mesocycle_id: uuid.UUID,
    payload: MesocyclePatch,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Mesocycle:
    db = _solo_entrenador(ctx)
    meso = _o_404(db, Mesocycle, mesocycle_id, "mesociclo")
    _aplicar(meso, payload.model_dump())
    db.commit()
    return meso


@editor.delete("/mesocycles/{mesocycle_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_mesociclo(
    mesocycle_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> None:
    db = _solo_entrenador(ctx)
    db.delete(_o_404(db, Mesocycle, mesocycle_id, "mesociclo"))
    db.commit()


# --- Sesión ---------------------------------------------------------------------


@editor.post(
    "/mesocycles/{mesocycle_id}/sessions",
    response_model=SessionCreated,
    status_code=status.HTTP_201_CREATED,
)
def crear_sesion(
    mesocycle_id: uuid.UUID,
    payload: SessionIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Session:
    db = _solo_entrenador(ctx)
    meso = _o_404(db, Mesocycle, mesocycle_id, "mesociclo")
    if payload.week_number > meso.week_count:
        # 409 y no 422: el número es válido, lo que no da es este bloque. Decirlo
        # así distingue "escribiste cualquier cosa" de "el mesociclo dura menos".
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"el mesociclo tiene {meso.week_count} semanas y pediste la {payload.week_number}",
        )
    sesion = Session(
        mesocycle_id=mesocycle_id,
        week_number=payload.week_number,
        day_number=payload.day_number,
        label=payload.label,
        scheduled_on=payload.scheduled_on,
    )
    db.add(sesion)
    db.commit()
    return sesion


@editor.patch("/sessions/{session_id}", response_model=SessionCreated)
def editar_sesion(
    session_id: uuid.UUID,
    payload: SessionPatch,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Session:
    db = _solo_entrenador(ctx)
    sesion = _o_404(db, Session, session_id, "sesión")
    _aplicar(sesion, payload.model_dump())
    db.commit()
    return sesion


@editor.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_sesion(
    session_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> None:
    db = _solo_entrenador(ctx)
    db.delete(_o_404(db, Session, session_id, "sesión"))
    db.commit()


# --- Prescripción ---------------------------------------------------------------


def _serie_desde(
    payload: PrescribedSetIn, prescription_id: uuid.UUID, numero: int
) -> PrescribedSet:
    """Una serie desde su carga útil, con el número que le toca.

    Vive acá y no repetida en el alta suelta y en la del lote: los `_dec` no son
    decoración —la columna es `numeric` y un `float` deja que Postgres redondee
    el binario— y una segunda copia es donde se olvida uno.
    """
    from app.api.routes import _dec

    return PrescribedSet(
        prescription_id=prescription_id,
        set_number=numero,
        reps_min=payload.reps_min,
        reps_max=payload.reps_max,
        rir_min=_dec(payload.rir_min),
        rir_max=_dec(payload.rir_max),
        target_load_kg=_dec(payload.target_load_kg),
        target_pct_1rm=_dec(payload.target_pct_1rm),
        tempo=payload.tempo,
        is_amrap=payload.is_amrap,
    )


@editor.post(
    "/sessions/{session_id}/prescriptions",
    response_model=PrescriptionOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_prescripcion(
    session_id: uuid.UUID,
    payload: PrescriptionIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Prescription:
    db = _solo_entrenador(ctx)
    _o_404(db, Session, session_id, "sesión")
    _o_404(db, Exercise, payload.exercise_id, "ejercicio")
    pres = Prescription(
        session_id=session_id,
        exercise_id=payload.exercise_id,
        position=payload.position
        or _siguiente(db, Prescription.position, Prescription.session_id == session_id),
        rest_seconds=payload.rest_seconds,
        coach_note=payload.coach_note,
        superset_key=payload.superset_key,
    )
    db.add(pres)

    # Un `flush` y no un `commit`: hace falta el id de la prescripción para
    # colgarle las series, y las dos cosas tienen que caer o quedar juntas. Con
    # dos commits, una serie que viola el CHECK de intensidad deja el ejercicio
    # creado y vacío, que es exactamente lo que el atleta ve como un día roto.
    db.flush()
    for i, serie in enumerate(payload.sets, start=1):
        db.add(_serie_desde(serie, pres.id, serie.set_number or i))

    db.commit()
    return pres


@editor.patch("/prescriptions/{prescription_id}", response_model=PrescriptionOut)
def editar_prescripcion(
    prescription_id: uuid.UUID,
    payload: PrescriptionPatch,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Prescription:
    db = _solo_entrenador(ctx)
    pres = _o_404(db, Prescription, prescription_id, "prescripción")
    _aplicar(pres, payload.model_dump())
    db.commit()
    return pres


@editor.delete("/prescriptions/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_prescripcion(
    prescription_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> None:
    db = _solo_entrenador(ctx)
    db.delete(_o_404(db, Prescription, prescription_id, "prescripción"))
    db.commit()


@editor.put("/sessions/{session_id}/prescriptions/order", response_model=list[PrescriptionOut])
def reordenar_prescripciones(
    session_id: uuid.UUID, payload: OrderIn, ctx: TenantContext = Depends(require_tenant_context)
) -> list[Prescription]:
    db = _solo_entrenador(ctx)
    _o_404(db, Session, session_id, "sesión")
    filas = list(
        db.scalars(select(Prescription).where(Prescription.session_id == session_id)).all()
    )
    _reordenar(db, filas, payload.ids, "position")
    db.commit()
    return sorted(filas, key=lambda p: p.position)


# --- Serie prescrita ------------------------------------------------------------


@editor.post(
    "/prescriptions/{prescription_id}/sets",
    response_model=PrescribedSetOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_serie(
    prescription_id: uuid.UUID,
    payload: PrescribedSetIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> PrescribedSet:
    db = _solo_entrenador(ctx)
    _o_404(db, Prescription, prescription_id, "prescripción")
    serie = _serie_desde(
        payload,
        prescription_id,
        payload.set_number
        or _siguiente(
            db, PrescribedSet.set_number, PrescribedSet.prescription_id == prescription_id
        ),
    )
    db.add(serie)
    db.commit()
    return serie


@editor.patch("/prescribed-sets/{set_id}", response_model=PrescribedSetOut)
def editar_serie(
    set_id: uuid.UUID,
    payload: PrescribedSetPatch,
    ctx: TenantContext = Depends(require_tenant_context),
) -> PrescribedSet:
    from app.api.routes import _dec

    db = _solo_entrenador(ctx)
    serie = _o_404(db, PrescribedSet, set_id, "serie")

    cambios = payload.model_dump(exclude={"autorregulada"})
    for campo in ("rir_min", "rir_max", "target_load_kg", "target_pct_1rm"):
        if cambios[campo] is not None:
            cambios[campo] = _dec(cambios[campo])
    if payload.is_amrap is not None:
        serie.is_amrap = payload.is_amrap
    cambios.pop("is_amrap")
    _aplicar(serie, cambios)

    if payload.autorregulada:
        # El peso lo elige el atleta ese día. Se borra acá y no mandando `None`
        # porque en una modificación parcial `None` es "no lo toques".
        serie.target_load_kg = None
        serie.target_pct_1rm = None

    db.commit()
    return serie


@editor.delete("/prescribed-sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_serie(set_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)) -> None:
    db = _solo_entrenador(ctx)
    db.delete(_o_404(db, PrescribedSet, set_id, "serie"))
    db.commit()


@editor.put("/prescriptions/{prescription_id}/sets/order", response_model=list[PrescribedSetOut])
def reordenar_series(
    prescription_id: uuid.UUID,
    payload: OrderIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> list[PrescribedSet]:
    db = _solo_entrenador(ctx)
    _o_404(db, Prescription, prescription_id, "prescripción")
    filas = list(
        db.scalars(
            select(PrescribedSet).where(PrescribedSet.prescription_id == prescription_id)
        ).all()
    )
    _reordenar(db, filas, payload.ids, "set_number")
    db.commit()
    return sorted(filas, key=lambda s: s.set_number)


# --- Catálogo de ejercicios -----------------------------------------------------


@editor.get("/exercises", response_model=list[ExerciseOut])
def listar_ejercicios(ctx: TenantContext = Depends(require_tenant_context)) -> list[ExerciseOut]:
    """La base común más los propios, con cuánto se usa cada uno.

    Qué ejercicios se ven lo deciden las policies: los de la base común no tienen
    dueño y se comparten, el resto es de quien lo creó. Repetir esa regla acá
    crearía una segunda copia que se desincroniza.

    El conteo de prescripciones viaja con cada uno porque la pantalla lo necesita
    **antes** de preguntar si borrar: una confirmación que no dice qué se lleva
    puesto no es una decisión informada, es un trámite.
    """
    usos = (
        select(Prescription.exercise_id, func.count().label("n"))
        .group_by(Prescription.exercise_id)
        .subquery()
    )
    filas = ctx.db.execute(
        select(Exercise, func.coalesce(usos.c.n, 0))
        .outerjoin(usos, usos.c.exercise_id == Exercise.id)
        .order_by(Exercise.name)
    ).all()
    return [
        ExerciseOut.model_validate(ej, from_attributes=True).model_copy(
            update={"prescription_count": n}
        )
        for ej, n in filas
    ]


@editor.post("/exercises", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED)
def crear_ejercicio(
    payload: ExerciseIn, ctx: TenantContext = Depends(require_tenant_context)
) -> Exercise:
    """A coach's own exercise. It lands in their catalogue, never in the global one.

    `coach_id` comes from the session and is not in the body: taking it from
    there would let somebody file an exercise into the shared catalogue, or into
    another coach's.
    """
    db = _solo_entrenador(ctx)
    if db.get(MovementPattern, payload.pattern_code) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"el patrón de movimiento '{payload.pattern_code}' no existe",
        )
    coach_id = db.scalar(text("SELECT id FROM coach WHERE user_id = app_current_user_id()"))
    ejercicio = Exercise(
        coach_id=coach_id,
        pattern_code=payload.pattern_code,
        name=payload.name,
        is_competition_lift=payload.is_competition_lift,
        video_url=payload.video_url,
        cues=payload.cues,
    )
    db.add(ejercicio)
    db.commit()
    return ejercicio


@editor.get("/movement-patterns", response_model=list[PatternOut])
def listar_patrones(ctx: TenantContext = Depends(require_tenant_context)) -> list[MovementPattern]:
    """The eleven patterns, which the editor needs to make the field selectable.

    They are a closed catalogue and not free text, which is what makes volume by
    pattern answerable at all.
    """
    return list(
        ctx.db.scalars(
            select(MovementPattern).order_by(MovementPattern.sort_order, MovementPattern.code)
        ).all()
    )


# --- Duplicar, que es lo que decide todo ----------------------------------------
#
# Es la razón por la que la planilla gana hoy. Copiar una semana entera con sus
# sesiones, sus ejercicios y sus series, y que la copia salga con la progresión
# que le corresponde por su posición en el bloque, sin tocarla a mano.


def _desplazamiento(meso: Mesocycle, desde: int, hasta: int) -> int:
    """Cuánto RIR mueve pasar de una semana a otra dentro del mismo bloque.

    La progresión se guarda como desplazamientos absolutos respecto de la primera
    semana, así que mover de W a T aplica la **diferencia** entre las dos
    posiciones. Eso es lo que hace que copiar de la 1 a la 2 no mueva nada y de
    la 2 a la 3 baje un punto, con la misma declaración.

    Lo que falte en la lista se lee como cero: un bloque que se extendió y todavía
    no declaró las semanas nuevas no progresa en ellas, que es más seguro que
    inventarle una continuación.
    """
    tabla = meso.rir_progression or []

    def en(semana: int) -> int:
        return tabla[semana - 1] if 1 <= semana <= len(tabla) else 0

    return en(hasta) - en(desde)


def _rir_movido(valor: Decimal | None, delta: int) -> Decimal | None:
    """El RIR corrido, sin bajar de cero.

    Cero es "sin repeticiones en reserva", o sea al fallo. No hay nada más duro
    que eso, y la columna lo impide con un CHECK — llegar ahí y seguir restando
    haría fallar la copia entera por una semana que ya estaba al máximo.
    """
    if valor is None:
        return None
    return max(Decimal(0), valor + delta)


def _copiar_serie(serie: PrescribedSet, prescripcion_id: uuid.UUID, delta: int) -> PrescribedSet:
    """La carga se copia igual, y eso no es pereza: es lo que pasa el 60% de las veces.

    Medido sobre la planilla, dentro de un mesociclo la carga se queda quieta en
    60 de cada 100 series y las repeticiones no cambian nunca. Lo que se mueve es
    el RIR. Mover la carga sola sería inventar una progresión que el entrenador no
    declaró.
    """
    return PrescribedSet(
        prescription_id=prescripcion_id,
        set_number=serie.set_number,
        reps_min=serie.reps_min,
        reps_max=serie.reps_max,
        rir_min=_rir_movido(serie.rir_min, delta),
        rir_max=_rir_movido(serie.rir_max, delta),
        target_load_kg=serie.target_load_kg,
        target_pct_1rm=serie.target_pct_1rm,
        tempo=serie.tempo,
        is_amrap=serie.is_amrap,
    )


def _copiar_prescripcion(
    db: OrmSession,
    pres: Prescription,
    sesion_id: uuid.UUID,
    delta: int,
    posicion: int | None = None,
) -> Prescription:
    """`posicion` se pasa cuando la copia cae en la misma sesión que el original.

    Copiar a otra sesión conserva el orden, que es lo que se quiere al duplicar
    una semana. Copiar dentro de la misma no puede: la posición ya está ocupada
    por quien se está copiando, y el `flush` la choca antes de que nadie la
    corrija después.
    """
    copia = Prescription(
        session_id=sesion_id,
        exercise_id=pres.exercise_id,
        position=posicion if posicion is not None else pres.position,
        rest_seconds=pres.rest_seconds,
        coach_note=pres.coach_note,
        superset_key=pres.superset_key,
    )
    db.add(copia)
    db.flush()
    for serie in sorted(pres.sets, key=lambda s: s.set_number):
        db.add(_copiar_serie(serie, copia.id, delta))
    return copia


def _copiar_sesion(
    db: OrmSession,
    sesion: Session,
    semana: int,
    dia: int,
    delta: int,
    mesociclo_id: uuid.UUID | None = None,
) -> Session:
    """`mesociclo_id` se pasa sólo al copiar hacia otro bloque.

    Por defecto la copia queda en el mesociclo del original, que es lo que quiere
    duplicar una semana. Clavarlo ahí impedía copiar un bloque entero.
    """
    copia = Session(
        mesocycle_id=mesociclo_id or sesion.mesocycle_id,
        week_number=semana,
        day_number=dia,
        label=sesion.label,
        # `scheduled_on` no se copia: la fecha era de la sesión original y
        # arrastrarla pondría la semana 3 en el día de la 2. Sin fecha es
        # correcto; una fecha vieja es una mentira.
    )
    db.add(copia)
    db.flush()
    for pres in sorted(sesion.prescriptions, key=lambda p: p.position):
        _copiar_prescripcion(db, pres, copia.id, delta)
    return copia


def _libre(db: OrmSession, mesocycle_id: uuid.UUID, semana: int, dias: set[int]) -> None:
    ocupados = set(
        db.scalars(
            select(Session.day_number).where(
                Session.mesocycle_id == mesocycle_id, Session.week_number == semana
            )
        ).all()
    )
    choque = sorted(dias & ocupados)
    if choque:
        # 409 y no un reemplazo silencioso: pisar una semana ya armada borra
        # trabajo sin preguntar, y el atleta puede haber registrado series ahí.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"la semana {semana} ya tiene sesiones en los días {choque}: borralas o elegí otra",
        )


@editor.post(
    "/mesocycles/{mesocycle_id}/duplicate-week",
    response_model=list[SessionCreated],
    status_code=status.HTTP_201_CREATED,
)
def duplicar_semana(
    mesocycle_id: uuid.UUID,
    payload: DuplicarSemanaIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> list[Session]:
    """Una semana entera sobre otra, con la progresión de la posición de destino."""
    db = _solo_entrenador(ctx)
    meso = _o_404(db, Mesocycle, mesocycle_id, "mesociclo")
    if payload.to_week > meso.week_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"el mesociclo tiene {meso.week_count} semanas y pediste la {payload.to_week}",
        )
    if payload.to_week == payload.from_week:
        raise HTTPException(status.HTTP_409_CONFLICT, "el origen y el destino son la misma semana")

    origen = list(
        db.scalars(
            select(Session)
            .where(Session.mesocycle_id == mesocycle_id, Session.week_number == payload.from_week)
            .order_by(Session.day_number)
        ).all()
    )
    if not origen:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"la semana {payload.from_week} no tiene sesiones"
        )

    _libre(db, mesocycle_id, payload.to_week, {s.day_number for s in origen})
    delta = _desplazamiento(meso, payload.from_week, payload.to_week)
    copias = [_copiar_sesion(db, s, payload.to_week, s.day_number, delta) for s in origen]
    db.commit()
    return copias


@editor.post(
    "/mesocycles/{mesocycle_id}/duplicate",
    response_model=MesocycleOut,
    status_code=status.HTTP_201_CREATED,
)
def duplicar_mesociclo(
    mesocycle_id: uuid.UUID,
    payload: DuplicarMesocicloIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Mesocycle:
    """Un bloque entero: o hacia uno nuevo, o dentro de uno que ya existe y está
    vacío.

    Las dos cosas por la misma ruta porque son la misma operación con distinto
    destino, igual que duplicar una semana. Sin destino crea el bloque siguiente;
    con destino, lo llena.

    **La progresión no se recalcula al cruzar de bloque.** El array de RIR es
    *interno* a un mesociclo —dice cuánto se mueve cada semana respecto de la
    primera de ese bloque—, así que aplicar un salto entre bloques distintos
    inventaría una progresión que nadie declaró. Las semanas se copian como
    están y el bloque nuevo declara la suya.
    """
    db = _solo_entrenador(ctx)
    origen = _o_404(db, Mesocycle, mesocycle_id, "mesociclo")

    if payload.to_mesocycle is not None:
        destino = _o_404(db, Mesocycle, payload.to_mesocycle, "mesociclo de destino")
        if destino.id == origen.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "el origen y el destino son el mismo bloque"
            )
        ocupado = db.scalars(
            select(Session.id).where(Session.mesocycle_id == destino.id).limit(1)
        ).first()
        if ocupado:
            # Igual que al pegar una semana: no se pisa trabajo hecho sin
            # preguntar, y el atleta puede haber registrado series ahí.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"el bloque «{destino.label}» ya tiene sesiones: borralas o elegí otro",
            )
    else:
        destino = Mesocycle(
            program_id=origen.program_id,
            ordinal=_siguiente(db, Mesocycle.ordinal, Mesocycle.program_id == origen.program_id),
            label=f"{origen.label} (copia)",
            week_count=origen.week_count,
            focus=origen.focus,
            rir_progression=origen.rir_progression,
        )
        db.add(destino)
        db.flush()

    sesiones = list(
        db.scalars(
            select(Session)
            .where(Session.mesocycle_id == origen.id)
            .order_by(Session.week_number, Session.day_number)
        ).all()
    )
    for s in sesiones:
        # Las semanas que el destino no tiene se descartan: copiar un bloque de
        # cuatro sobre uno de tres dejaría sesiones en una semana que no existe,
        # y el editor no las dibujaría nunca.
        if s.week_number <= destino.week_count:
            _copiar_sesion(db, s, s.week_number, s.day_number, 0, destino.id)

    db.commit()
    return destino


@editor.post(
    "/sessions/{session_id}/duplicate",
    response_model=SessionCreated,
    status_code=status.HTTP_201_CREATED,
)
def duplicar_sesion(
    session_id: uuid.UUID,
    payload: DuplicarSesionIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Session:
    db = _solo_entrenador(ctx)
    sesion = _o_404(db, Session, session_id, "sesión")
    meso = _o_404(db, Mesocycle, sesion.mesocycle_id, "mesociclo")
    if payload.to_week > meso.week_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"el mesociclo tiene {meso.week_count} semanas y pediste la {payload.to_week}",
        )
    _libre(db, sesion.mesocycle_id, payload.to_week, {payload.to_day})
    delta = _desplazamiento(meso, sesion.week_number, payload.to_week)
    copia = _copiar_sesion(db, sesion, payload.to_week, payload.to_day, delta)
    db.commit()
    return copia


@editor.post(
    "/prescriptions/{prescription_id}/duplicate",
    response_model=PrescriptionOut,
    status_code=status.HTTP_201_CREATED,
)
def duplicar_prescripcion(
    prescription_id: uuid.UUID, ctx: TenantContext = Depends(require_tenant_context)
) -> Prescription:
    """El ejercicio con su bloque de series, al final de la misma sesión.

    Sin progresión: quedarse en la misma sesión es quedarse en la misma semana, y
    el desplazamiento entre una posición y sí misma es cero.
    """
    db = _solo_entrenador(ctx)
    pres = _o_404(db, Prescription, prescription_id, "prescripción")
    copia = _copiar_prescripcion(
        db,
        pres,
        pres.session_id,
        0,
        posicion=_siguiente(db, Prescription.position, Prescription.session_id == pres.session_id),
    )
    db.commit()
    return copia


@editor.patch("/exercises/{exercise_id}", response_model=ExerciseOut)
def editar_ejercicio(
    exercise_id: uuid.UUID,
    payload: ExercisePatch,
    ctx: TenantContext = Depends(require_tenant_context),
) -> Exercise:
    """Corregir un ejercicio propio.

    Uno del catálogo global contesta 404 y no 403, y eso no es esconder el
    motivo: las policies lo dejan fuera del alcance de esta escritura, así que
    para esta operación la fila no existe. Es la misma respuesta que da el
    ejercicio de otro entrenador, que es exactamente lo que se quiere.
    """
    db = _solo_entrenador(ctx)
    ejercicio = _o_404(db, Exercise, exercise_id, "ejercicio")
    if ejercicio.coach_id is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "el catálogo global se lee, no se edita: duplicá el ejercicio y editá tu copia",
        )
    if payload.pattern_code is not None and db.get(MovementPattern, payload.pattern_code) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"el patrón de movimiento '{payload.pattern_code}' no existe",
        )
    _aplicar(ejercicio, payload.model_dump())
    db.commit()
    return ejercicio


@editor.delete("/exercises/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_ejercicio(
    exercise_id: uuid.UUID,
    confirmar: bool = False,
    ctx: TenantContext = Depends(require_tenant_context),
) -> None:
    """Borra el ejercicio y lo saca de los días que lo incluyen.

    Sin `confirmar`, uno que está prescrito contesta 409 diciendo en cuántos
    lugares. Esa respuesta es la que le da a la pantalla el número para preguntar
    con sentido — «esto no se puede deshacer» sin decir qué se lleva no es una
    decisión, es un trámite. Y deja la API a salvo por defecto: un cliente que no
    pregunte no arrasa un programa por descuido.

    **Lo que el atleta registró sobrevive.** Al borrar la prescripción se van sus
    series prescritas, pero `logged_set` quedó con `ON DELETE SET NULL` y con su
    copia congelada de lo que se le pidió, así que el registro no se pierde:
    queda sin plan al que pertenecer, que es exactamente lo que pasó. Sin ese
    cambio esta cascada se llevaría el entrenamiento de una persona por limpiar
    un catálogo.
    """
    db = _solo_entrenador(ctx)
    ejercicio = _o_404(db, Exercise, exercise_id, "ejercicio")
    if ejercicio.coach_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "el catálogo global se lee, no se borra")

    en_uso = db.scalar(
        select(func.count())
        .select_from(Prescription)
        .where(Prescription.exercise_id == ejercicio.id)
    )
    if en_uso and not confirmar:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"está prescrito en {en_uso} lugar(es): confirmá para sacarlo de todos",
        )
    if en_uso:
        db.execute(delete(Prescription).where(Prescription.exercise_id == ejercicio.id))
        # Un `DELETE` bloqueado por una policy `RESTRICTIVE` no levanta error:
        # devuelve cero filas y sigue. Así que las prescripciones que cuelgan de
        # un vínculo archivado sobreviven en silencio, y el borrado del ejercicio
        # se estrella después contra `prescription_exercise_id_fkey`, que es
        # RESTRICT — un 500 que no explica nada, sobre una operación que la
        # persona confirmó.
        #
        # Se vuelve a contar en vez de mirar el predicado de la policy: lo que
        # importa no es cuáles *deberían* haberse ido sino cuáles siguen ahí, y
        # eso lo contesta la base. El conteo las ve porque ninguna restrictiva
        # toca el `SELECT`.
        quedan = db.scalar(
            select(func.count())
            .select_from(Prescription)
            .where(Prescription.exercise_id == ejercicio.id)
        )
        if quedan:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{quedan} de sus {en_uso} prescripciones cuelgan de un vínculo "
                f"archivado y no se pueden sacar: reactivá ese vínculo o dejá el ejercicio",
            )
    db.delete(ejercicio)
    db.commit()


@editor.delete("/movement-patterns/{code}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_patron(code: str, ctx: TenantContext = Depends(require_tenant_context)) -> None:
    """Borra un patrón propio.

    No se borra en cascada, al revés que un ejercicio, y la diferencia es de
    escala: un ejercicio se lleva sus prescripciones, un patrón se llevaría todos
    los ejercicios que lo usan **y** las prescripciones de todos ellos. Eso es
    demasiado para una confirmación, así que se pide desarmarlo antes.

    La base común no se toca desde acá: se cambia con una migración, que es una
    decisión visible y revisada.
    """
    db = _solo_entrenador(ctx)
    patron = db.get(MovementPattern, code)
    if patron is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "patrón inexistente")
    if patron.coach_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "la base común se lee, no se borra")

    en_uso = db.scalar(
        select(func.count()).select_from(Exercise).where(Exercise.pattern_code == code)
    )
    if en_uso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{en_uso} ejercicio(s) lo usan: cambiales el patrón antes de borrarlo",
        )
    db.delete(patron)
    db.commit()


@editor.post("/movement-patterns", response_model=PatternOut, status_code=status.HTTP_201_CREATED)
def crear_patron(
    payload: PatternIn, ctx: TenantContext = Depends(require_tenant_context)
) -> MovementPattern:
    """Un patrón de movimiento nuevo, del entrenador que lo crea.

    Los once que trajo la planilla no tienen dueño y son la base común: un
    entrenador nuevo los necesita para no arrancar con un desplegable vacío. Lo
    que agrega cada uno es suyo y no aparece en el catálogo de nadie más, igual
    que un ejercicio propio — dos entrenadores nombran distinto lo mismo, y
    compartirlos ensucia el catálogo de los dos.

    El código se deriva del nombre en vez de pedirse. Pedir los dos es pedir dos
    veces lo mismo y dejar que se contradigan.
    """
    db = _solo_entrenador(ctx)
    raiz = _codigo_de(payload.label_es)
    if not raiz:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "el nombre no deja ningún código utilizable: usá letras o números",
        )

    coach_id = db.scalar(text("SELECT id FROM coach WHERE user_id = app_current_user_id()"))
    ya_lo_tiene = db.scalar(
        select(MovementPattern.code).where(
            MovementPattern.label_es.ilike(payload.label_es.strip()),
            (MovementPattern.coach_id == coach_id) | (MovementPattern.coach_id.is_(None)),
        )
    )
    if ya_lo_tiene:
        raise HTTPException(status.HTTP_409_CONFLICT, "ya tenés un patrón con ese nombre")

    ultimo = db.scalar(select(func.max(MovementPattern.sort_order))) or 0
    patron = _insertar_con_codigo_libre(db, raiz, payload, coach_id, ultimo + 1)
    db.commit()
    return patron


def _insertar_con_codigo_libre(
    db: OrmSession, raiz: str, payload: PatternIn, coach_id: uuid.UUID | None, orden: int
) -> MovementPattern:
    """Inserta, y si el código está tomado prueba el siguiente.

    `code` es la clave primaria de toda la tabla —`exercise.pattern_code` apunta
    ahí— así que sigue siendo único de punta a punta aunque las filas tengan
    dueño. Dos entrenadores que crean «Antebrazo» terminan con `antebrazo` y
    `antebrazo_2`, y ninguno ve un código: la interfaz muestra `label_es`.

    Se prueba en vez de consultar primero, y eso no es pereza. Una consulta que
    busque códigos tomados corre bajo las policies y **no ve el del otro
    entrenador**, así que devolvería uno libre que en realidad no lo está — es el
    error que tuvo la primera versión de esto. Esquivar las policies para
    mirarlas sería filtrar que existe algo ajeno. Y aunque se pudiera consultar,
    entre la consulta y el `INSERT` cabe el de otra persona: el choque hay que
    saber manejarlo igual.

    Cada intento va en su savepoint. Sin eso, el primer rechazo aborta la
    transacción entera y el reintento falla por un motivo que no es el suyo.
    """
    for intento in range(1, 100):
        codigo = raiz if intento == 1 else f"{raiz}_{intento}"[:64]
        punto = db.begin_nested()
        patron = MovementPattern(
            code=codigo,
            label_es=payload.label_es.strip(),
            is_compound=payload.is_compound,
            sort_order=orden,
            coach_id=coach_id,
        )
        db.add(patron)
        try:
            punto.commit()
        except IntegrityError:
            # Revertir el savepoint ya saca la instancia de la sesión: pedirle a
            # SQLAlchemy que además la olvide falla porque no la tiene.
            punto.rollback()
            continue
        return patron
    raise HTTPException(
        status.HTTP_409_CONFLICT, "hay demasiados patrones con ese nombre: elegí otro"
    )


def _codigo_de(nombre: str) -> str:
    """El nombre, sin acentos ni signos, en minúsculas y con guiones bajos.

    Sigue la forma de los once que ya existen —`bisagra_de_cadera_isquios`— para
    que un catálogo mezclado no se lea como dos.
    """
    import re
    import unicodedata

    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", plano.lower())).strip("_")[:64]
