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
from typing import TYPE_CHECKING, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import TenantContext, require_tenant_context
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
    ExerciseIn,
    ExerciseOut,
    MesocycleIn,
    MesocycleOut,
    MesocyclePatch,
    OrderIn,
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
    if ctx.role != "coach":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "sólo un entrenador edita rutinas")
    return ctx.db


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
    from app.api.routes import _dec

    db = _solo_entrenador(ctx)
    _o_404(db, Prescription, prescription_id, "prescripción")
    serie = PrescribedSet(
        prescription_id=prescription_id,
        set_number=payload.set_number
        or _siguiente(
            db, PrescribedSet.set_number, PrescribedSet.prescription_id == prescription_id
        ),
        reps_min=payload.reps_min,
        reps_max=payload.reps_max,
        rir_min=_dec(payload.rir_min),
        rir_max=_dec(payload.rir_max),
        target_load_kg=_dec(payload.target_load_kg),
        target_pct_1rm=_dec(payload.target_pct_1rm),
        tempo=payload.tempo,
        is_amrap=payload.is_amrap,
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
def listar_ejercicios(ctx: TenantContext = Depends(require_tenant_context)) -> list[Exercise]:
    """The global catalogue plus the caller's own.

    No filtering happens here: which exercises are visible is decided by the
    policies — the global ones have no owner and are shared, and the rest belong
    to whoever created them. Repeating that rule in Python would create a second
    copy that drifts.
    """
    return list(ctx.db.scalars(select(Exercise).order_by(Exercise.name)).all())


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
