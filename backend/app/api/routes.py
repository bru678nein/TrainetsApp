from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.domain.analytics import SetRecord, adherence_by_week, weekly_volume
from app.domain.rpe import OutOfChartError, estimate_1rm
from app.models import (
    Athlete,
    LoggedSet,
    Mesocycle,
    PrescribedSet,
    Prescription,
    Program,
    Session,
)
from app.schemas import (
    AdherenceOut,
    AthleteOut,
    ExerciseBlock,
    LogSetIn,
    LogSetOut,
    SessionOut,
    SessionSummary,
    SetOut,
    VolumeOut,
)

router = APIRouter(prefix="/api")


def _dec(value: float | None) -> Decimal | None:
    """Las columnas `numeric` se mapean a `Decimal`.

    Pasar el `float` que llega por JSON haría que Postgres redondee un float8;
    convertir por `str` conserva exactamente lo que mandó el cliente.
    """
    return None if value is None else Decimal(str(value))


def _athlete_or_404(db: OrmSession, athlete_id: uuid.UUID) -> Athlete:
    a = db.get(Athlete, athlete_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "atleta inexistente")
    return a


def _records(db: OrmSession, athlete_id: uuid.UUID) -> list[SetRecord]:
    """Aplana el árbol relacional al dataclass que consume el dominio."""
    stmt = (
        select(PrescribedSet, Prescription, Session, LoggedSet)
        .join(Prescription, Prescription.id == PrescribedSet.prescription_id)
        .join(Session, Session.id == Prescription.session_id)
        .join(Mesocycle, Mesocycle.id == Session.mesocycle_id)
        .join(Program, Program.id == Mesocycle.program_id)
        .outerjoin(LoggedSet, LoggedSet.prescribed_set_id == PrescribedSet.id)
        .where(Program.athlete_id == athlete_id)
        .options(selectinload(Prescription.exercise))
    )
    out = []
    for ps, pr, se, log in db.execute(stmt).all():
        out.append(
            SetRecord(
                week=se.week_number,
                pattern=pr.exercise.pattern_code,
                exercise=pr.exercise.name,
                reps_min=ps.reps_min,
                reps_max=ps.reps_max,
                rir_min=float(ps.rir_min) if ps.rir_min is not None else None,
                rir_max=float(ps.rir_max) if ps.rir_max is not None else None,
                reps_done=log.reps if log else None,
                load_kg=float(log.load_kg) if log and log.load_kg is not None else None,
                rir_done=float(log.rir) if log and log.rir is not None else None,
                skipped=bool(log.was_skipped) if log else False,
            )
        )
    return out


@router.get("/athletes", response_model=list[AthleteOut])
def list_athletes(db: OrmSession = Depends(get_db)) -> Sequence[Athlete]:
    return db.scalars(select(Athlete).where(Athlete.is_active)).all()


@router.get("/athletes/{athlete_id}/sessions", response_model=list[SessionSummary])
def list_sessions(athlete_id: uuid.UUID, db: OrmSession = Depends(get_db)) -> list[SessionSummary]:
    """Agenda del atleta: una fila por sesión, sin las series.

    Existe para que el `id` de la sesión sea descubrible. Antes el detalle se
    pedía por `(semana, día)`, pero `week_number` es relativo al mesociclo:
    esa combinación matchea una sesión por meso y la ruta devolvía la primera
    según un ORDER BY, en silencio.

    El orden es por programa, después mesociclo, después semana y día. Ordenar
    sólo por `Mesocycle.ordinal` intercalaría los mesociclos de dos programas
    distintos, porque el ordinal es único por programa y no por atleta.
    """
    _athlete_or_404(db, athlete_id)
    stmt = (
        select(Session, Mesocycle, Program)
        .join(Mesocycle, Mesocycle.id == Session.mesocycle_id)
        .join(Program, Program.id == Mesocycle.program_id)
        .where(Program.athlete_id == athlete_id)
        .order_by(
            Program.starts_on,
            Program.id,
            Mesocycle.ordinal,
            Session.week_number,
            Session.day_number,
        )
    )
    return [
        SessionSummary(
            id=se.id,
            program_id=pr.id,
            program=pr.name,
            mesocycle=me.label,
            mesocycle_ordinal=me.ordinal,
            week_number=se.week_number,
            day_number=se.day_number,
            label=se.label,
            scheduled_on=se.scheduled_on,
        )
        for se, me, pr in db.execute(stmt).all()
    ]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, db: OrmSession = Depends(get_db)) -> SessionOut:
    """La vista que abre el atleta en el gimnasio.

    No verifica de quién es la sesión: hoy no hay identidad con la cual
    compararla. Esa verificación es el criterio de aceptación 3 de la spec 001
    y va con RLS abajo, no como un `if` acá.
    """
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(
            selectinload(Session.prescriptions)
            .selectinload(Prescription.sets)
            .selectinload(PrescribedSet.log),
            selectinload(Session.prescriptions).selectinload(Prescription.exercise),
            selectinload(Session.mesocycle),
        )
    )
    se = db.scalars(stmt).first()
    if se is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sesión inexistente")
    blocks = [
        ExerciseBlock(
            prescription_id=pr.id,
            exercise=pr.exercise.name,
            pattern=pr.exercise.pattern_code,
            rest_seconds=pr.rest_seconds,
            coach_note=pr.coach_note,
            sets=[
                SetOut(
                    id=s.id,
                    set_number=s.set_number,
                    reps_min=s.reps_min,
                    reps_max=s.reps_max,
                    rir_min=s.rir_min,
                    rir_max=s.rir_max,
                    target_load_kg=s.target_load_kg,
                    reps_done=s.log.reps if s.log else None,
                    load_done_kg=s.log.load_kg if s.log else None,
                    rir_done=s.log.rir if s.log else None,
                )
                for s in pr.sets
            ],
        )
        for pr in se.prescriptions
    ]
    return SessionOut(
        id=se.id,
        mesocycle=se.mesocycle.label,
        mesocycle_ordinal=se.mesocycle.ordinal,
        week_number=se.week_number,
        day_number=se.day_number,
        blocks=blocks,
    )


@router.put("/sets/{set_id}/log", response_model=LogSetOut)
def log_set(set_id: uuid.UUID, payload: LogSetIn, db: OrmSession = Depends(get_db)) -> LoggedSet:
    """Idempotente: el atleta corrige una serie tantas veces como quiera.

    Tampoco verifica que la serie sea del atleta que la registra — no hay
    identidad todavía. Es el criterio de aceptación 4 de la spec 001.
    """
    ps = db.get(PrescribedSet, set_id)
    if ps is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serie inexistente")

    # Hoy esto no puede devolver None: toda la cadena prescribed_set →
    # prescription → session → mesocycle → program → athlete_id es NOT NULL, así
    # que si la serie existe su programa existe. Se contempla igual porque bajo
    # RLS (feature 001) deja de ser cierto: la serie puede ser visible y el
    # programa no, y el join queda vacío.
    #
    # En ese caso la respuesta correcta es 404 con el mismo mensaje que una
    # serie inexistente. Es el criterio de aceptación 2 de la spec 001: un
    # identificador ajeno no se distingue de uno que no existe.
    athlete_id = db.scalars(
        select(Program.athlete_id)
        .join(Mesocycle)
        .join(Session)
        .join(Prescription)
        .where(Prescription.id == ps.prescription_id)
    ).one_or_none()
    if athlete_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serie inexistente")

    e1rm: float | None = None
    # `is not None` y no truthiness: reps=0 (falló la serie) y load_kg=0 (peso
    # corporal) son registros válidos y con `and` se salteaban en silencio.
    if payload.reps is not None and payload.load_kg is not None and payload.rir is not None:
        try:
            e1rm = estimate_1rm(payload.load_kg, payload.reps, payload.rir)
        except (OutOfChartError, ValueError):
            e1rm = None  # más de 12 reps o carga 0: fuera de tabla, no es un error

    log = db.scalars(select(LoggedSet).where(LoggedSet.prescribed_set_id == set_id)).first()
    if log is None:
        log = LoggedSet(prescribed_set_id=set_id, athlete_id=athlete_id)
        db.add(log)
    log.reps, log.load_kg, log.rir = payload.reps, _dec(payload.load_kg), _dec(payload.rir)
    log.was_skipped, log.athlete_note, log.e1rm_kg = payload.was_skipped, payload.note, _dec(e1rm)
    db.commit()
    return log


@router.get("/athletes/{athlete_id}/volume", response_model=list[VolumeOut])
def volume(athlete_id: uuid.UUID, db: OrmSession = Depends(get_db)) -> list[VolumeOut]:
    _athlete_or_404(db, athlete_id)
    return [
        VolumeOut(
            week=v.week,
            pattern=v.pattern,
            sets_planned=v.sets_planned,
            sets_done=v.sets_done,
            tonnage_kg=round(v.tonnage_kg, 1),
        )
        for v in weekly_volume(_records(db, athlete_id))
    ]


@router.get("/athletes/{athlete_id}/adherence", response_model=list[AdherenceOut])
def adherence(athlete_id: uuid.UUID, db: OrmSession = Depends(get_db)) -> list[AdherenceOut]:
    _athlete_or_404(db, athlete_id)
    return [
        AdherenceOut(
            week=a.week,
            sets_planned=a.sets_planned,
            sets_done=a.sets_done,
            completion_rate=round(a.completion_rate, 4),
            in_range_rate=round(a.in_range_rate, 4),
            tonnage_kg=round(a.tonnage_kg, 1),
            avg_rir_deviation=round(a.avg_rir_deviation, 3)
            if a.avg_rir_deviation is not None
            else None,
        )
        for a in adherence_by_week(_records(db, athlete_id))
    ]
