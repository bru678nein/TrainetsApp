from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload

from app.api.deps import (
    TenantContext,
    require_identity_for_signup,
    require_tenant_context,
    solo_entrenador_al_dia,
    tenant_session,
)
from app.domain.analytics import (
    SetRecord,
    adherence_by_pattern,
    adherence_by_week,
    load_progression,
    weekly_volume,
)
from app.domain.rpe import OutOfChartError, estimate_1rm
from app.models import (
    AppUser,
    Athlete,
    Coach,
    Exercise,
    Invitation,
    LoggedSet,
    Mesocycle,
    PrescribedSet,
    Prescription,
    Program,
    Session,
)
from app.schemas import (
    AceptarInvitacionIn,
    AdherenceOut,
    AthleteCreated,
    AthleteIn,
    AthleteOut,
    CambioDeEstadoIn,
    CoachOut,
    EstadoOut,
    ExerciseBlock,
    InvitacionAceptada,
    InvitacionCreada,
    LoadPointOut,
    LoadProgressionOut,
    LogSetIn,
    LogSetOut,
    PatternAdherenceOut,
    SessionOut,
    SessionSummary,
    SetOut,
    VolumeOut,
)

# The dependency goes on the router, not on each endpoint.
#
# Every route hanging off this one resolves identity and role before its handler
# runs, including the ones that never touch the database — and those are exactly
# the ones that would otherwise ship unprotected, because the protection used to
# arrive as a side effect of asking for a session.
#
# Declared here rather than repeated per endpoint, forgetting stops being an
# omitted line and becomes creating a second router and mounting it: an act
# that is visible in any review.
#
# FastAPI caches dependencies per request, so an endpoint that also declares
# `Depends(tenant_session)` resolves the context once, not twice.
router = APIRouter(prefix="/api", dependencies=[Depends(require_tenant_context)])


def _flo(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _dec(value: float | None) -> Decimal | None:
    """`numeric` columns map to `Decimal`.

    Passing the `float` that arrives over JSON would make Postgres round a
    float8; converting via `str` preserves exactly what the client sent.
    """
    return None if value is None else Decimal(str(value))


def _athlete_or_404(db: OrmSession, athlete_id: uuid.UUID) -> Athlete:
    a = db.get(Athlete, athlete_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "atleta inexistente")
    return a


def _records(db: OrmSession, athlete_id: uuid.UUID) -> list[SetRecord]:
    """Flatten the relational tree into the dataclass the domain consumes."""
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
        # Contra qué se compara: lo congelado si la serie se ejecutó, lo vigente
        # si todavía no. Una serie sin registro no tiene pasado que respetar, así
        # que corregirla mueve su objetivo, que es lo que el entrenador quiere.
        # Una que sí lo tiene se compara contra lo que le pidieron ese día.
        contra = log if log is not None and log.week_number is not None else None
        out.append(
            SetRecord(
                week=contra.week_number if contra else se.week_number,
                pattern=contra.pattern_code if contra else pr.exercise.pattern_code,
                exercise=contra.exercise_name if contra else pr.exercise.name,
                reps_min=contra.prescribed_reps_min if contra else ps.reps_min,
                reps_max=contra.prescribed_reps_max if contra else ps.reps_max,
                rir_min=_flo(contra.prescribed_rir_min if contra else ps.rir_min),
                rir_max=_flo(contra.prescribed_rir_max if contra else ps.rir_max),
                reps_done=log.reps if log else None,
                load_kg=float(log.load_kg) if log and log.load_kg is not None else None,
                rir_done=float(log.rir) if log and log.rir is not None else None,
                skipped=bool(log.was_skipped) if log else False,
            )
        )
    return out


def _congelar_lo_prescrito(db: OrmSession, log: LoggedSet, ps: PrescribedSet) -> None:
    """Copia sobre el registro contra qué se ejecutó, y en qué semana y ejercicio.

    La semana y el ejercicio no son para la comparación: son para que el registro
    siga siendo legible el día que su prescripción deje de existir. Sin ellos, un
    registro huérfano es un número sin contexto.
    """
    fila = db.execute(
        select(Session.week_number, Exercise.pattern_code, Exercise.name)
        .join(Prescription, Prescription.session_id == Session.id)
        .join(Exercise, Exercise.id == Prescription.exercise_id)
        .where(Prescription.id == ps.prescription_id)
    ).one_or_none()

    log.prescribed_reps_min, log.prescribed_reps_max = ps.reps_min, ps.reps_max
    log.prescribed_rir_min, log.prescribed_rir_max = ps.rir_min, ps.rir_max
    log.prescribed_load_kg = ps.target_load_kg
    if fila is not None:
        log.week_number, log.pattern_code, log.exercise_name = fila


def _coach_del_contexto(db: OrmSession, ctx: TenantContext) -> Coach:
    """The caller's own coaching space.

    Resolved from the identity rather than taken from the request, which is what
    keeps an athlete from being filed into somebody else's space. Under RLS the
    policy would refuse that write anyway — `athlete_as_coach`'s WITH CHECK
    requires the `coach_id` to be one the caller owns — so this is the readable
    half of a rule the database also enforces.
    """
    coach = db.scalars(
        select(Coach)
        .join(AppUser, AppUser.id == Coach.user_id)
        .where(AppUser.auth_user_id == ctx.identity.auth_user_id)
    ).first()
    if coach is None:
        # Reachable only if the role check passed and the profile vanished
        # in between, which means somebody deleted it mid-request.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no tenés un espacio de entrenador")
    return coach


@router.post("/athletes", response_model=AthleteCreated, status_code=status.HTTP_201_CREATED)
def crear_atleta(
    payload: AthleteIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> AthleteCreated:
    """A record for somebody who has no account yet.

    The central case, not an edge one: the coach builds the whole programme
    before the athlete signs up, which is how they work today with a spreadsheet
    they share afterwards. So `user_id` stays NULL, and the person claims the
    record later through an invitation link.
    """
    solo_entrenador_al_dia(ctx, "sólo un entrenador crea fichas")
    db = ctx.db
    coach = _coach_del_contexto(db, ctx)

    atleta = Athlete(
        coach_id=coach.id,
        user_id=None,
        full_name=payload.full_name.strip(),
        email=payload.email,
        birth_date=payload.birth_date,
        bodyweight_kg=_dec(payload.bodyweight_kg),
        level=payload.level,
        goal=payload.goal,
        notes=payload.notes,
    )
    db.add(atleta)
    db.commit()
    return AthleteCreated(
        id=atleta.id,
        full_name=atleta.full_name,
        level=atleta.level,
        has_account=atleta.user_id is not None,
    )


@router.get("/athletes", response_model=list[AthleteOut])
def list_athletes(
    incluir_cerrados: bool = False, db: OrmSession = Depends(tenant_session)
) -> list[AthleteOut]:
    """Los vínculos vigentes, y bajo pedido también los que no lo están.

    El default sigue siendo sólo los activos: es la lista con la que el
    entrenador trabaja todos los días, y meter ahí a los archivados la convierte
    en un registro histórico. Pero pausar tiene que poder deshacerse, y un
    listado que nunca los muestra deja al vínculo pausado invisible y sin botón
    para reanudarlo.

    Explícito y no automático, porque son dos preguntas distintas: "¿con quién
    estoy trabajando?" y "¿a quién entrené alguna vez?".
    """
    filtro = "" if incluir_cerrados else "WHERE a.estado = 'activo'"
    # Una sola consulta para todo el listado, y no una por atleta. Con veinte
    # fichas, tres subconsultas correlacionadas por fila son sesenta viajes a la
    # base en la pantalla que más se abre — el mismo error que ya está declarado
    # como deuda en la analítica, que carga todo en memoria.
    #
    # Correlacionadas y no `JOIN` con `GROUP BY`: cada una devuelve una fila o
    # ninguna, y agrupar obligaría a agregar campos que no se agregan, como el
    # nombre del programa.
    filas = db.execute(
        text(f"""
        SELECT a.id, a.full_name, a.level, a.estado,
               a.user_id IS NOT NULL AS tiene_cuenta,
               (SELECT max(l.performed_at) FROM logged_set l
                 WHERE l.athlete_id = a.id) AS ultima_sesion,
               p.name AS programa_actual,
               -- La semana la trae congelada `logged_set` desde la 0016, así que
               -- no hace falta subir por prescribed_set → prescription → session.
               -- Es la del último registro y no el máximo: `week_number` es
               -- relativa al mesociclo, así que el máximo daría casi siempre la
               -- última del bloque, entrene cuando entrene.
               (SELECT l.week_number FROM logged_set l
                 WHERE l.athlete_id = a.id AND l.week_number IS NOT NULL
                 ORDER BY l.performed_at DESC LIMIT 1) AS semana_actual,
               (SELECT m.week_count FROM mesocycle m
                 WHERE m.program_id = p.id
                 ORDER BY m.ordinal DESC LIMIT 1) AS semanas_del_bloque
          FROM athlete a
          LEFT JOIN LATERAL (
              SELECT pr.id, pr.name FROM program pr
               WHERE pr.athlete_id = a.id AND pr.status = 'active'
               ORDER BY pr.starts_on DESC NULLS LAST, pr.created_at DESC
               LIMIT 1
          ) p ON true
          {filtro}
         ORDER BY a.estado, a.full_name
    """)
    ).mappings()
    return [AthleteOut(**fila) for fila in filas]


@router.get("/athletes/{athlete_id}/sessions", response_model=list[SessionSummary])
def list_sessions(
    athlete_id: uuid.UUID, db: OrmSession = Depends(tenant_session)
) -> list[SessionSummary]:
    """The athlete's schedule: one row per session, without the sets.

    It exists so the session `id` is discoverable. The detail used to be fetched
    by `(week, day)`, but `week_number` is relative to the mesocycle: that pair
    matches one session per mesocycle and the route silently returned the first
    one by ORDER BY.

    Ordering is by program, then mesocycle, then week and day. Ordering by
    `Mesocycle.ordinal` alone would interleave the mesocycles of two different
    programs, because the ordinal is unique per program and not per athlete.
    """
    _athlete_or_404(db, athlete_id)
    # Las dos cuentas van en la misma consulta y no una por sesión: un mesociclo
    # de cuatro semanas por tres días son doce viajes a la base para dibujar una
    # lista.
    prescritas = (
        select(func.count(PrescribedSet.id))
        .join(Prescription, Prescription.id == PrescribedSet.prescription_id)
        .where(Prescription.session_id == Session.id)
        .correlate(Session)
        .scalar_subquery()
    )
    respondidas = (
        select(func.count(LoggedSet.id))
        .join(PrescribedSet, PrescribedSet.id == LoggedSet.prescribed_set_id)
        .join(Prescription, Prescription.id == PrescribedSet.prescription_id)
        .where(Prescription.session_id == Session.id)
        .correlate(Session)
        .scalar_subquery()
    )
    stmt = (
        select(Session, Mesocycle, Program, prescritas, respondidas)
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
            mesocycle_id=me.id,
            mesocycle=me.label,
            mesocycle_ordinal=me.ordinal,
            week_number=se.week_number,
            day_number=se.day_number,
            label=se.label,
            scheduled_on=se.scheduled_on,
            series_prescritas=pide,
            series_respondidas=hechas,
        )
        for se, me, pr, pide, hechas in db.execute(stmt).all()
    ]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, db: OrmSession = Depends(tenant_session)) -> SessionOut:
    """The view the athlete opens at the gym.

    It does not check who owns the session: there is no identity to compare it
    against yet. That check belongs with RLS underneath, not as an `if` here.
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
def log_set(
    set_id: uuid.UUID, payload: LogSetIn, db: OrmSession = Depends(tenant_session)
) -> LoggedSet:
    """Idempotent: the athlete can correct a set as many times as they want.

    It also does not check that the set belongs to the athlete logging it —
    there is no identity yet; the policies enforce it.
    """
    ps = db.get(PrescribedSet, set_id)
    if ps is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serie inexistente")

    # Today this cannot return None: the whole chain prescribed_set →
    # prescription → session → mesocycle → program → athlete_id is NOT NULL, so
    # if the set exists its program exists. It is handled anyway because under
    # RLS that stops being true: the set may be visible and the
    # program not, leaving the join empty.
    #
    # In that case the correct answer is 404 with the same message as a
    # non-existent set, so that someone else's identifier is indistinguishable
    # from one that does not exist.
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
    # `is not None` rather than truthiness: reps=0 (failed set) and load_kg=0
    # (bodyweight) are valid records, and `and` skipped them silently.
    if payload.reps is not None and payload.load_kg is not None and payload.rir is not None:
        try:
            e1rm = estimate_1rm(payload.load_kg, payload.reps, payload.rir)
        except (OutOfChartError, ValueError):
            e1rm = None  # over 12 reps or zero load: off the chart, not an error

    log = db.scalars(select(LoggedSet).where(LoggedSet.prescribed_set_id == set_id)).first()
    if log is None:
        log = LoggedSet(prescribed_set_id=set_id, athlete_id=athlete_id)
        db.add(log)
        # Lo prescrito se congela **una sola vez**, cuando el registro nace, y no
        # se refresca al corregirlo. Es lo que hace que la adherencia no se mueva
        # hacia atrás: el entrenador sube el objetivo un mes después y el 100% de
        # la persona sigue siendo 100%, porque se compara contra lo que le
        # pidieron ese día. Refrescarlo acá sería reescribir el pasado desde el
        # único lugar que lo tenía guardado.
        _congelar_lo_prescrito(db, log, ps)
    log.reps, log.load_kg, log.rir = payload.reps, _dec(payload.load_kg), _dec(payload.rir)
    log.was_skipped, log.athlete_note, log.e1rm_kg = payload.was_skipped, payload.note, _dec(e1rm)
    db.commit()
    return log


@router.post("/athletes/{athlete_id}/estado", response_model=EstadoOut)
def cambiar_estado(
    athlete_id: uuid.UUID,
    payload: CambioDeEstadoIn,
    ctx: TenantContext = Depends(require_tenant_context),
) -> EstadoOut:
    """Pause, resume, archive or reactivate a link.

    One endpoint and not four, because which transitions are legal is already
    decided in one place — the domain's table — and four routes would re-decide
    it in four.

    The role check is explicit and not left to the policies. An athlete's policy
    on their own record permits updating it, which would let them archive
    themselves; athlete-initiated departure is out of scope, so the refusal has
    to be here.
    """
    from app.domain.vinculo import Accion, Estado, Rechazo, transicionar

    solo_entrenador_al_dia(ctx, "sólo un entrenador cambia el vínculo")

    db = ctx.db
    ficha = _athlete_or_404(db, athlete_id)
    resultado = transicionar(Estado(ficha.estado), Accion(payload.accion))
    if isinstance(resultado, Rechazo):
        # 409 y no 400: lo que se pidió es válido, el vínculo es el que no está
        # en condiciones de recibirlo. El motivo viaja tal como lo nombra el
        # dominio, que es lo que distingue "eso ya está hecho" de "reactivalo
        # primero".
        raise HTTPException(status.HTTP_409_CONFLICT, resultado.value)

    ficha.estado = resultado.value
    db.commit()
    return EstadoOut(athlete_id=ficha.id, estado=ficha.estado)


@router.post(
    "/athletes/{athlete_id}/invitation",
    response_model=InvitacionCreada,
    status_code=status.HTTP_201_CREATED,
)
def generar_invitacion(
    athlete_id: uuid.UUID,
    ctx: TenantContext = Depends(require_tenant_context),
) -> InvitacionCreada:
    """A link the coach sends so the athlete can claim an existing record.

    The clear token is returned here and nowhere else: the table stores its
    SHA-256, and no route can show it again. Losing it means generating another,
    which also invalidates this one — the behaviour wanted anyway.

    Revoking whatever was pending is not politeness. The partial unique index
    admits one usable invitation per record, so issuing without revoking simply
    does not commit, and the rule that a new link makes the old one useless is
    guaranteed by the schema rather than by remembering.
    """
    from app.domain.invitacion import emitir

    solo_entrenador_al_dia(ctx, "sólo un entrenador invita")

    db = ctx.db
    ficha = _athlete_or_404(db, athlete_id)
    if ficha.estado == "archivado":
        raise HTTPException(status.HTTP_409_CONFLICT, "vinculo_archivado")

    ahora = datetime.now(UTC)
    db.execute(
        update(Invitation)
        .where(
            Invitation.athlete_id == ficha.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=ahora)
    )
    token, guardable = emitir(ahora)
    db.add(
        Invitation(
            athlete_id=ficha.id,
            token_hash=guardable.token_hash,
            expires_at=guardable.expires_at,
        )
    )
    db.commit()
    return InvitacionCreada(token=token, expires_at=guardable.expires_at)


@router.get("/athletes/{athlete_id}/volume", response_model=list[VolumeOut])
def volume(athlete_id: uuid.UUID, db: OrmSession = Depends(tenant_session)) -> list[VolumeOut]:
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
def adherence(
    athlete_id: uuid.UUID, db: OrmSession = Depends(tenant_session)
) -> list[AdherenceOut]:
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


@router.get("/athletes/{athlete_id}/adherence/by-pattern", response_model=list[PatternAdherenceOut])
def adherence_por_patron(
    athlete_id: uuid.UUID, db: OrmSession = Depends(tenant_session)
) -> list[PatternAdherenceOut]:
    """Adherence grouped where the answer is, worst first.

    By week, an athlete who does everything except hamstrings reads as 90% and
    says nothing. By pattern, the hamstrings sit at 72% against 99% for the rest,
    and that is something a coach can act on.

    The ordering is part of the answer and is decided here rather than in the
    browser: sorting by worst compliance puts the problem at the top without
    anybody looking for it, and alphabetical hides it among the ones that comply.
    """
    _athlete_or_404(db, athlete_id)
    return [
        PatternAdherenceOut(
            pattern=a.pattern,
            sets_planned=a.sets_planned,
            sets_done=a.sets_done,
            completion_rate=round(a.completion_rate, 4),
            in_range_rate=round(a.in_range_rate, 4),
            avg_rir_deviation=round(a.avg_rir_deviation, 3)
            if a.avg_rir_deviation is not None
            else None,
        )
        for a in adherence_by_pattern(_records(db, athlete_id))
    ]


@router.get("/athletes/{athlete_id}/progression", response_model=list[LoadProgressionOut])
def progression(
    athlete_id: uuid.UUID, db: OrmSession = Depends(tenant_session)
) -> list[LoadProgressionOut]:
    """Heaviest load lifted per exercise and week.

    Built from the prescriptions and not from the logs, which is what keeps a
    week with nothing recorded visible as a gap. Assembling it from what the
    athlete logged would silently drop those weeks, and a gap that disappears
    reads as an exercise that was not programmed.
    """
    _athlete_or_404(db, athlete_id)
    return [
        LoadProgressionOut(
            exercise=nombre,
            points=[
                LoadPointOut(week=semana, load_kg=round(carga, 1) if carga is not None else None)
                for semana, carga in semanas.items()
            ],
        )
        for nombre, semanas in load_progression(_records(db, athlete_id)).items()
    ]


# Second router, and the only one that does not demand a role.
#
# It exists because of a chicken and egg: `require_tenant_context` answers 403 to
# anybody without the role, so a brand-new identity could never reach the
# endpoint that would give them one. Kept apart rather than punching a hole in
# the data router — an exception that lives in its own mount is one a reviewer
# can see, and `tests/conftest.py` lists it explicitly so the route walks treat
# it as the exception it is instead of silently skipping it.
alta = APIRouter(prefix="/api/me", dependencies=[Depends(require_identity_for_signup)])


@alta.post("/coach", response_model=CoachOut, status_code=status.HTTP_201_CREATED)
def alta_de_entrenador(ctx: TenantContext = Depends(require_identity_for_signup)) -> CoachOut:
    """First login: the person gets their identity and an empty coaching space.

    Idempotent. A client that retries, or a first login racing a second tab,
    gets the same space back rather than a second one — and `coach.user_id` is
    UNIQUE, so the database would refuse the duplicate anyway. Answering 201
    either way keeps the client from having to tell the two apart.

    Nothing here checks who the caller is. The `app_user` policy does it:
    its WITH CHECK admits exactly one row, the caller's own, so an `if` in
    Python would be decoration over the thing actually enforcing it.
    """
    db = ctx.db
    persona = db.scalars(
        select(AppUser).where(AppUser.auth_user_id == ctx.identity.auth_user_id)
    ).first()

    if persona is None:
        if ctx.profile is None:
            # `app_user.email` is NOT NULL and the token did not carry one.
            # Inventing it is worse than stopping — the same call migration 0002
            # made rather than making up an address for an athlete.
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "el token no trae email: no se puede crear la identidad",
            )
        persona = AppUser(
            auth_user_id=ctx.identity.auth_user_id,
            email=ctx.profile.email,
            display_name=ctx.profile.display_name,
        )
        db.add(persona)
        db.flush()

    coach = db.scalars(select(Coach).where(Coach.user_id == persona.id)).first()
    if coach is None:
        coach = Coach(user_id=persona.id)
        db.add(coach)
        db.flush()

    atletas = db.scalars(select(Athlete).where(Athlete.coach_id == coach.id)).all()
    db.commit()
    return CoachOut(
        id=coach.id,
        display_name=persona.display_name,
        athlete_count=len(atletas),
        puede_importar=coach.puede_importar,
    )


@router.get("/coach", response_model=CoachOut)
def mi_espacio(ctx: TenantContext = Depends(require_tenant_context)) -> CoachOut:
    """El espacio del entrenador que está pidiendo.

    Existía sólo el alta, así que la interfaz no tenía de dónde leer nada del
    entrenador — ni siquiera su propio nombre. Se agrega ahora porque la beta del
    importador necesita que el front sepa si ofrecerlo, y ofrecerlo siempre para
    que el servidor conteste 403 es exactamente lo que esta aplicación no hace.

    Contesta 404 y no 403 a quien todavía no es entrenador: no tener espacio no
    es un permiso denegado, es que no existe.
    """
    db = ctx.db
    fila = (
        db.execute(
            text("""
        SELECT c.id, u.display_name, c.puede_importar,
               (SELECT count(*) FROM athlete a WHERE a.coach_id = c.id) AS athlete_count
          FROM coach c JOIN app_user u ON u.id = c.user_id
         -- Por `u.id` y no por `u.auth_user_id`: `app_current_user_id()` traduce
         -- el `sub` del token a la fila de `app_user` y devuelve **su id**, no el
         -- `sub`. Comparado contra `auth_user_id` no coincide nunca, y el modo de
         -- falla es un 404 para todo el mundo, que se lee como «no sos
         -- entrenador» en vez de como una consulta mal escrita.
         WHERE u.id = app_current_user_id()
    """)
        )
        .mappings()
        .first()
    )
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "todavía no tenés un espacio de entrenador")
    return CoachOut(**fila)


#: Cada rechazo con su código. Distinguibles a propósito: un link vencido no se
#: confunde con uno inválido, porque a quien lo recibió le dice qué hacer —pedir
#: otro— y a un atacante no le sirve, ya que el vencido no vale. `410` y no
#: `404` es exactamente esa distinción, en el vocabulario que HTTP ya tiene.
_RECHAZOS = {
    "inexistente": (status.HTTP_404_NOT_FOUND, "invitacion_inexistente"),
    "vencida": (status.HTTP_410_GONE, "invitacion_vencida"),
    "usada": (status.HTTP_409_CONFLICT, "invitacion_usada"),
    "ya_vinculado": (status.HTTP_409_CONFLICT, "ya_sos_atleta_de_ese_entrenador"),
    # `410` como la vencida y no `404`: el link existió y el vínculo se cerró.
    # Se distingue de `inexistente` porque las salidas son distintas — una se
    # arregla pidiendo otro link, ésta sólo si el entrenador reactiva.
    "vinculo_archivado": (status.HTTP_410_GONE, "vinculo_archivado"),
}


@alta.post("/invitation", response_model=InvitacionAceptada)
def aceptar_invitacion(
    payload: AceptarInvitacionIn,
    ctx: TenantContext = Depends(require_identity_for_signup),
) -> InvitacionAceptada:
    """The athlete claims a record the coach already built.

    Hangs off the signup router and not the data one, and that is forced rather
    than chosen: whoever accepts holds an identity and no link to the record yet,
    so there is no active role to demand and no tenant context to set.

    The identity is resolved here because creating one needs the email and the
    name, which travel in the token. Everything that has to be atomic — checking
    the invitation is neither revoked, spent nor expired, and associating — is
    one call into `app_aceptar_invitacion`, the only place in the system that
    writes across the tenant boundary.
    """
    from app.domain.invitacion import hash_de

    db = ctx.db
    persona = db.scalars(
        select(AppUser).where(AppUser.auth_user_id == ctx.identity.auth_user_id)
    ).first()
    if persona is None:
        if ctx.profile is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "el token no trae email: no se puede crear la identidad",
            )
        persona = AppUser(
            auth_user_id=ctx.identity.auth_user_id,
            email=ctx.profile.email,
            display_name=ctx.profile.display_name,
        )
        db.add(persona)
        db.flush()

    resultado = db.execute(
        text("SELECT app_aceptar_invitacion(:h, :u)"),
        {"h": hash_de(payload.token), "u": persona.id},
    ).scalar_one()

    if resultado != "aceptada":
        # La identidad recién creada se conserva aunque la invitación falle: la
        # persona existe igual, y borrarla obligaría a recrearla en el reintento
        # con otro id.
        db.commit()
        codigo, detalle = _RECHAZOS[resultado]
        raise HTTPException(codigo, detalle)

    db.commit()
    return InvitacionAceptada(resultado="aceptada")
