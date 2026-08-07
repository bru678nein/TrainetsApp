-- =============================================================================
--  Coaching platform — esquema base (PostgreSQL 16+)
--  Derivado del modelo de dominio real de una planilla en producción:
--  1.326 series, 59 ejercicios, 11 patrones de movimiento, 17 semanas.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- -----------------------------------------------------------------------------
-- Tenancy: el coach es el tenant. Todo cuelga de él.
-- -----------------------------------------------------------------------------
CREATE TABLE coach (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id  text UNIQUE NOT NULL,        -- sub del JWT del proveedor de auth
    email         citext UNIQUE NOT NULL,
    display_name  text NOT NULL,
    locale        text NOT NULL DEFAULT 'es-AR',
    unit_system   text NOT NULL DEFAULT 'metric'
                  CHECK (unit_system IN ('metric','imperial')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE athlete (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id      uuid NOT NULL REFERENCES coach(id) ON DELETE CASCADE,
    auth_user_id  text UNIQUE,                 -- NULL hasta que el atleta activa su cuenta
    full_name     text NOT NULL,
    email         citext,
    birth_date    date,
    bodyweight_kg numeric(5,2),
    level         text CHECK (level IN ('principiante','intermedio','avanzado')),
    goal          text,
    notes         text,
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX athlete_coach_idx ON athlete (coach_id) WHERE is_active;

-- -----------------------------------------------------------------------------
-- Catálogo de ejercicios.
-- El patrón es NOT NULL a propósito: en la planilla original 354 de 1.326 series
-- quedaron sin clasificar por ser opcional, y sin patrón no hay análisis de volumen.
-- -----------------------------------------------------------------------------
CREATE TABLE movement_pattern (
    code          text PRIMARY KEY,            -- 'empuje_horizontal', 'bisagra_cadera'
    label_es      text NOT NULL,
    is_compound   boolean NOT NULL DEFAULT true,
    sort_order    smallint NOT NULL DEFAULT 0
);

CREATE TABLE exercise (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id      uuid REFERENCES coach(id) ON DELETE CASCADE,  -- NULL = catálogo global
    pattern_code  text NOT NULL REFERENCES movement_pattern(code),
    name          text NOT NULL,
    is_competition_lift boolean NOT NULL DEFAULT false,         -- SQ / BP / DL
    parent_id     uuid REFERENCES exercise(id),                 -- variante de un básico
    video_url     text,
    cues          text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
-- Un coach no puede repetir nombre; el catálogo global tampoco.
CREATE UNIQUE INDEX exercise_name_scope_idx
    ON exercise (COALESCE(coach_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(name));
CREATE INDEX exercise_pattern_idx ON exercise (pattern_code);

-- -----------------------------------------------------------------------------
-- Jerarquía de programación: program > mesocycle > session > prescription
-- Sin nombres de bloque libres: orden numérico + label editable.
-- (En la planilla los bloques se llamaban "1.3", "2.3", "H1" y era inservible.)
-- -----------------------------------------------------------------------------
CREATE TABLE program (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id      uuid NOT NULL REFERENCES coach(id) ON DELETE CASCADE,
    athlete_id    uuid NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    name          text NOT NULL,
    starts_on     date,
    status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft','active','completed','archived')),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX program_athlete_idx ON program (athlete_id, status);

CREATE TABLE mesocycle (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id    uuid NOT NULL REFERENCES program(id) ON DELETE CASCADE,
    ordinal       smallint NOT NULL,           -- 1, 2, 3...
    label         text NOT NULL,               -- 'Acumulación', renombrable
    week_count    smallint NOT NULL CHECK (week_count BETWEEN 1 AND 16),
    focus         text,
    UNIQUE (program_id, ordinal)
);

CREATE TABLE session (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    mesocycle_id  uuid NOT NULL REFERENCES mesocycle(id) ON DELETE CASCADE,
    week_number   smallint NOT NULL CHECK (week_number >= 1),   -- dentro del mesociclo
    day_number    smallint NOT NULL CHECK (day_number >= 1),    -- sesión 1..n de esa semana
    label         text,
    scheduled_on  date,
    UNIQUE (mesocycle_id, week_number, day_number)
);

-- Un ejercicio dentro de una sesión.
CREATE TABLE prescription (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    uuid NOT NULL REFERENCES session(id) ON DELETE CASCADE,
    exercise_id   uuid NOT NULL REFERENCES exercise(id),
    position      smallint NOT NULL,
    superset_key  text,                        -- misma clave = se alternan
    rest_seconds  int CHECK (rest_seconds >= 0),
    coach_note    text,                        -- 'FÍLMATE', 'completá las reps'
    UNIQUE (session_id, position)
);
CREATE INDEX prescription_session_idx ON prescription (session_id);

-- -----------------------------------------------------------------------------
-- La serie prescrita. ESTE es el grano correcto, no el ejercicio:
-- en los datos reales la carga cambia entre series de un mismo ejercicio
-- (registros del tipo "30kg x6 / 25kg x7 / 20kg x10").
--
-- La carga es polimórfica — la planilla usaba las tres formas mezcladas:
--   absoluta   -> target_load_kg = 80
--   relativa   -> target_pct_1rm = 0.75
--   autorregulada -> sólo rir_min/rir_max, el atleta elige el peso
-- -----------------------------------------------------------------------------
CREATE TABLE prescribed_set (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prescription_id uuid NOT NULL REFERENCES prescription(id) ON DELETE CASCADE,
    set_number      smallint NOT NULL CHECK (set_number >= 1),
    reps_min        smallint CHECK (reps_min >= 0),
    reps_max        smallint CHECK (reps_max >= 0),
    rir_min         numeric(3,1) CHECK (rir_min >= 0),
    rir_max         numeric(3,1) CHECK (rir_max >= 0),
    target_load_kg  numeric(6,2) CHECK (target_load_kg >= 0),
    target_pct_1rm  numeric(4,3) CHECK (target_pct_1rm > 0 AND target_pct_1rm <= 1.5),
    tempo           text,                      -- '3-1-0'
    is_amrap        boolean NOT NULL DEFAULT false,
    UNIQUE (prescription_id, set_number),
    CONSTRAINT reps_range_ok CHECK (reps_max IS NULL OR reps_min IS NULL OR reps_max >= reps_min),
    CONSTRAINT rir_range_ok  CHECK (rir_max  IS NULL OR rir_min  IS NULL OR rir_max  >= rir_min),
    -- No se puede prescribir carga absoluta y relativa a la vez.
    CONSTRAINT load_not_ambiguous CHECK (NOT (target_load_kg IS NOT NULL AND target_pct_1rm IS NOT NULL))
);

-- -----------------------------------------------------------------------------
-- La serie ejecutada. Tabla separada de la prescripción a propósito:
-- en la planilla ambas vivían en la misma fila y por eso el dato se ensuciaba
-- (la columna "Kg" a veces era el plan y a veces lo que el atleta llegó a hacer).
-- -----------------------------------------------------------------------------
CREATE TABLE logged_set (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prescribed_set_id uuid NOT NULL REFERENCES prescribed_set(id) ON DELETE CASCADE,
    athlete_id        uuid NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    performed_at      timestamptz NOT NULL DEFAULT now(),
    reps              smallint CHECK (reps >= 0),
    load_kg           numeric(6,2) CHECK (load_kg >= 0),
    rir               numeric(3,1) CHECK (rir >= 0),
    was_skipped       boolean NOT NULL DEFAULT false,
    athlete_note      text,
    -- e1RM con la tabla RPE (Epley como fallback). Se calcula en la app y se
    -- persiste para no recomputar 1M de filas en cada consulta de progreso.
    e1rm_kg           numeric(6,2),
    UNIQUE (prescribed_set_id)
);
CREATE INDEX logged_set_athlete_time_idx ON logged_set (athlete_id, performed_at DESC);

-- Tabla de coeficientes RPE x reps. Dato de referencia, versionado por si cambia.
CREATE TABLE rpe_coefficient (
    rpe           numeric(3,1) NOT NULL CHECK (rpe BETWEEN 6 AND 10),
    reps          smallint NOT NULL CHECK (reps BETWEEN 1 AND 12),
    pct_1rm       numeric(4,3) NOT NULL CHECK (pct_1rm > 0 AND pct_1rm <= 1),
    PRIMARY KEY (rpe, reps)
);

-- -----------------------------------------------------------------------------
-- Vista de volumen semanal por patrón: la métrica que la planilla nunca calculó.
-- -----------------------------------------------------------------------------
CREATE VIEW weekly_volume AS
SELECT
    p.athlete_id,
    p.id                                    AS program_id,
    m.ordinal                               AS mesocycle_ordinal,
    s.week_number,
    e.pattern_code,
    count(*) FILTER (WHERE l.id IS NOT NULL AND NOT l.was_skipped) AS sets_done,
    count(*)                                                        AS sets_planned,
    sum(l.reps * l.load_kg)                                         AS tonnage_kg,
    avg(l.rir)                                                      AS avg_rir
FROM prescribed_set ps
JOIN prescription pr ON pr.id = ps.prescription_id
JOIN session      s  ON s.id  = pr.session_id
JOIN mesocycle    m  ON m.id  = s.mesocycle_id
JOIN program      p  ON p.id  = m.program_id
JOIN exercise     e  ON e.id  = pr.exercise_id
LEFT JOIN logged_set l ON l.prescribed_set_id = ps.id
GROUP BY p.athlete_id, p.id, m.ordinal, s.week_number, e.pattern_code;

-- -----------------------------------------------------------------------------
-- Aislamiento por tenant con RLS. app.current_coach_id lo setea el middleware
-- de FastAPI en cada request, después de validar el JWT.
-- -----------------------------------------------------------------------------
ALTER TABLE athlete ENABLE ROW LEVEL SECURITY;
ALTER TABLE program ENABLE ROW LEVEL SECURITY;

CREATE POLICY athlete_tenant_isolation ON athlete
    USING (coach_id = current_setting('app.current_coach_id', true)::uuid);

CREATE POLICY program_tenant_isolation ON program
    USING (coach_id = current_setting('app.current_coach_id', true)::uuid);
