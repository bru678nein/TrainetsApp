from __future__ import annotations

import uuid

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
    SetOut,
    VolumeOut,
)

router = APIRouter(prefix="/api")


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
def list_athletes(db: OrmSession = Depends(get_db)):
    return db.scalars(select(Athlete).where(Athlete.is_active)).all()


@router.get("/athletes/{athlete_id}/sessions/{week}/{day}", response_model=SessionOut)
def get_session(athlete_id: uuid.UUID, week: int, day: int, db: OrmSession = Depends(get_db)):
    """La vista que abre el atleta en el gimnasio."""
    _athlete_or_404(db, athlete_id)
    stmt = (
        select(Session)
        .join(Mesocycle)
        .join(Program)
        .where(
            Program.athlete_id == athlete_id, Session.week_number == week, Session.day_number == day
        )
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
        week_number=se.week_number,
        day_number=se.day_number,
        blocks=blocks,
    )


@router.put("/sets/{set_id}/log", response_model=LogSetOut)
def log_set(set_id: uuid.UUID, payload: LogSetIn, db: OrmSession = Depends(get_db)):
    """Idempotente: el atleta corrige una serie tantas veces como quiera."""
    ps = db.get(PrescribedSet, set_id)
    if ps is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serie inexistente")
    athlete_id = db.scalars(
        select(Program.athlete_id)
        .join(Mesocycle)
        .join(Session)
        .join(Prescription)
        .where(Prescription.id == ps.prescription_id)
    ).first()

    e1rm = None
    if payload.reps and payload.load_kg and payload.rir is not None:
        try:
            e1rm = estimate_1rm(payload.load_kg, payload.reps, payload.rir)
        except (OutOfChartError, ValueError):
            e1rm = None  # más de 12 reps: fuera de la tabla RPE, no es un error

    log = db.scalars(select(LoggedSet).where(LoggedSet.prescribed_set_id == set_id)).first()
    if log is None:
        log = LoggedSet(prescribed_set_id=set_id, athlete_id=athlete_id)
        db.add(log)
    log.reps, log.load_kg, log.rir = payload.reps, payload.load_kg, payload.rir
    log.was_skipped, log.athlete_note, log.e1rm_kg = payload.was_skipped, payload.note, e1rm
    db.commit()
    return log


@router.get("/athletes/{athlete_id}/volume", response_model=list[VolumeOut])
def volume(athlete_id: uuid.UUID, db: OrmSession = Depends(get_db)):
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
def adherence(athlete_id: uuid.UUID, db: OrmSession = Depends(get_db)):
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
