-- =============================================================================
--  Coaching platform — esquema base (PostgreSQL 16+)
--  Derivado del modelo de dominio real de una planilla en producción:
--  1.326 series, 59 ejercicios, 11 patrones de movimiento, 17 semanas.
--
--  DOCUMENTO DE REFERENCIA — NO SE APLICA.
--  El esquema real lo definen backend/app/models.py y las migraciones de
--  Alembic en backend/migrations/. Este archivo se conserva porque explica
--  por qué el modelo es como es; los comentarios son el registro de las
--  decisiones. Para el DDL vigente: `alembic upgrade head --sql`.
--
--  El RLS del final YA está aplicado: migraciones 0004 a 0013. Lo de abajo es
--  el bosquejo que explica la forma; el DDL vigente son las migraciones, que
--  traen 37 policies: 19 permisivas y 18 restrictivas. Ante una diferencia, manda la migración.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "citext";

-- -----------------------------------------------------------------------------
-- Identidad y roles. El coach sigue siendo el tenant, pero la persona ya no es
-- el coach: una misma identidad puede ser entrenador de sus atletas y, a la vez,
-- atleta de varios entrenadores.
--
-- Hasta la migración 0002 cada rol traía su identidad pegada —`auth_user_id` en
-- `coach` y en `athlete`, cada uno con su UNIQUE global— y eso permitía una sola
-- ficha de atleta por persona para toda la vida del sistema. Lo que lo forzó no
-- fue el entrenador que se entrena solo, sino cualquiera que cambie de
-- entrenador: el vínculo anterior se archiva en vez de borrarse, así
-- que el nuevo necesita una ficha más mientras la vieja sobrevive.
-- -----------------------------------------------------------------------------
CREATE TABLE app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id  text UNIQUE NOT NULL,        -- sub del JWT del proveedor de auth
    email         citext UNIQUE NOT NULL,
    display_name  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE coach (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- UNIQUE: a lo sumo un perfil de entrenador por persona. Lo que sí puede
    -- repetirse es el rol de atleta.
    user_id       uuid UNIQUE NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    -- Preferencias del espacio de trabajo, no de la persona: por eso no viven
    -- en app_user.
    locale        text NOT NULL DEFAULT 'es-AR',
    unit_system   text NOT NULL DEFAULT 'metric'
                  CHECK (unit_system IN ('metric','imperial')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE athlete (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id      uuid NOT NULL REFERENCES coach(id) ON DELETE CASCADE,
    -- NULL = ficha sin cuenta todavía. Es el caso central, no el borde: el
    -- entrenador arma el programa entero antes de que el atleta se registre.
    --
    -- SET NULL y no CASCADE: borrar la identidad no puede borrar el historial de
    -- entrenamiento, que también es el trabajo del entrenador.
    user_id       uuid REFERENCES app_user(id) ON DELETE SET NULL,
    -- Se queda acá y no en app_user: es lo que el entrenador escribe a mano
    -- cuando la persona todavía no existe como identidad.
    full_name     text NOT NULL,
    email         citext,
    birth_date    date,
    bodyweight_kg numeric(5,2),
    level         text CHECK (level IN ('principiante','intermedio','avanzado')),
    goal          text,
    notes         text,
    -- Tres estados y no un booleano. `pausado` esconde al atleta del listado y
    -- deja todo editable; `archivado` cierra el vínculo y nadie
    -- escribe debajo de él.
    estado        text NOT NULL DEFAULT 'activo'
                  CHECK (estado IN ('activo','pausado','archivado')),
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX athlete_coach_idx ON athlete (coach_id) WHERE estado = 'activo';


-- Una persona es a lo sumo un atleta de un entrenador dado, pero puede serlo de
-- varios entrenadores. Parcial y no UNIQUE normal: `user_id` es NULL en toda
-- ficha sin cuenta y en Postgres los NULL no colisionan entre sí, así que un
-- UNIQUE común parecería cubrir esto y no cubriría nada.
CREATE UNIQUE INDEX athlete_coach_user_uq
    ON athlete (coach_id, user_id) WHERE user_id IS NOT NULL;

-- Invitación para que el atleta reclame una ficha que ya existe. Es nuestra y no
-- del proveedor de auth: la ficha existe antes que la cuenta, y las invitaciones
-- del proveedor obligan al orden inverso (ADR 0003).
CREATE TABLE invitation (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    athlete_id  uuid NOT NULL REFERENCES athlete(id) ON DELETE CASCADE,
    -- El SHA-256, nunca el token. Una filtración de esta tabla no entrega links
    -- vivos, y buscar por índice no filtra información por tiempo de respuesta.
    token_hash  bytea NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- Guardado y no calculado: derivado al leer, cambiar los siete días movería
    -- el vencimiento de links que ya están en manos de alguien.
    expires_at  timestamptz NOT NULL,
    accepted_at timestamptz,
    accepted_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
    revoked_at  timestamptz
);
CREATE UNIQUE INDEX invitation_token_uq ON invitation (token_hash);
-- A lo sumo una invitación usable por ficha. Emitir una nueva obliga a revocar
-- la anterior en la misma transacción, así que el criterio 3 lo garantiza el
-- esquema y no la memoria de quien programa.
CREATE UNIQUE INDEX invitation_pendiente_uq ON invitation (athlete_id)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;

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
    -- e1RM con la tabla RPE. Se calcula en la app y se persiste para no
    -- recomputar 1M de filas en cada consulta de progreso.
    -- No hay fallback de Epley: fuera de la tabla (más de 12 reps, RPE < 6)
    -- queda NULL. Estimar con una fórmula distinta a la que usó el resto de
    -- las series haría incomparables dos números de la misma columna.
    e1rm_kg           numeric(6,2),
    UNIQUE (prescribed_set_id)
);
CREATE INDEX logged_set_athlete_time_idx ON logged_set (athlete_id, performed_at DESC);

-- DESCARTADA. Acá iba una tabla `rpe_coefficient` con los coeficientes
-- RPE x reps. No existe: los coeficientes viven en backend/app/domain/rpe.py,
-- como diccionario.
--
-- El motivo es que el dominio no depende de infraestructura. Calcula e1RM sin
-- I/O y se testea sin levantar base; leer los coeficientes de una tabla lo
-- habría obligado a recibir una sesión de SQLAlchemy, que es exactamente lo
-- que el artículo prohíbe. El argumento a favor era "versionado por si cambia",
-- pero la tabla RPE de RTS no cambió en quince años, y si cambiara sería un
-- cambio de dominio que merece pasar por code review, no un UPDATE.
--
-- Se deja escrito en vez de borrado porque este archivo es el registro de las
-- decisiones, y una decisión revertida sin rastro es la que alguien vuelve a
-- proponer en seis meses.

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
-- Aislamiento por tenant con RLS. APLICADO: migraciones 0004 y 0005.
--
-- Este archivo no se aplica nunca, así que lo de abajo es el bosquejo que
-- explica la forma; el DDL vigente son las migraciones, que traen 37 policies: 19 permisivas y 18 restrictivas.
-- Si las dos difieren, manda la migración y esto es un bug de documentación.
--
-- El contrato de la sesión son dos variables, siempre las dos, ninguna con
-- default:
--
--   app.current_auth_user_id  text  -- el `sub` del JWT, verificado
--   app.active_role           text  -- 'coach' | 'athlete', del header Active-Role
--
-- `active_role` y no `current_role`: CURRENT_ROLE es palabra reservada, y
-- `SET LOCAL app.current_role = 'coach'` es error de sintaxis aun con prefijo.
-- La trampa es que current_setting('app.current_role') SÍ compila adentro de la
-- policy, porque ahí es un literal: el DDL entra sin quejarse y la app revienta
-- recién en runtime.
--
-- La variable lleva el `sub` y no app_user.id, que parece un rodeo y evita un
-- punto muerto: traducir uno en otro exige leer `app_user`, y esa lectura pasa
-- ANTES de que exista contexto.
-- -----------------------------------------------------------------------------

-- Las variables NO se leen crudas. `current_setting` sin segundo argumento
-- explota si nunca se seteó, pero una variable custom no vuelve a estar
-- indefinida: `SET LOCAL` revierte al terminar la transacción y lo que queda es
-- la cadena vacía. O sea que a partir del segundo request de una conexión del
-- pool, un contexto olvidado se leería como '' y la respuesta serían cero filas
-- en silencio. Estas dos funciones lo convierten en un error (migración 0005).
CREATE FUNCTION app_auth_user_id() RETURNS text LANGUAGE plpgsql STABLE AS $$
DECLARE valor text;
BEGIN
    valor := current_setting('app.current_auth_user_id');
    IF valor = '' THEN
        RAISE EXCEPTION 'app.current_auth_user_id vacío' USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN valor;
END $$;
-- app_active_role() es igual, y además exige que el valor sea 'coach' o 'athlete'.

CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT u.id FROM app_user u WHERE u.auth_user_id = app_auth_user_id()
$$;

-- Las cinco tablas profundas —mesocycle, session, prescription, prescribed_set,
-- logged_set— NO recorren la cadena adentro de la policy. Se probó y no escala:
-- RLS también se aplica dentro de las subconsultas de una policy, así que leer
-- `prescription` desde la policy de `prescribed_set` dispara la policy de
-- `prescription`, que dispara la de `session`, y el costo se multiplica por
-- nivel. Medido contra la planilla real, 1.326 series:
--
--     athlete (0 niveles)          0,14 ms
--     prescription (4 niveles)     1.143 ms
--     prescribed_set (5 niveles)   más de 20 s, cancelado
--
-- El recorrido va adentro de una función SECURITY DEFINER, que corre como el
-- dueño y por eso no dispara policies: la recursión se corta. Misma consulta,
-- 60 ms. Devuelven booleanos y nunca ids, tienen search_path fijado, y EXECUTE
-- revocado de PUBLIC — bypassean RLS por diseño y eso hay que acotarlo.
CREATE FUNCTION app_coach_ve_prescribed_set(uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
    SELECT EXISTS (
        SELECT 1 FROM prescribed_set x
        JOIN prescription pr ON pr.id = x.prescription_id
        JOIN session s ON s.id = pr.session_id
        JOIN mesocycle m ON m.id = s.mesocycle_id
        JOIN program p ON p.id = m.program_id
        JOIN coach c ON c.id = p.coach_id AND c.user_id = app_current_user_id()
        WHERE x.id = $1)
$$;
-- ...y una por cada (tabla profunda, rol): diez en total.

-- Diez tablas con ENABLE + FORCE. `movement_pattern` es referencia pura y queda
-- sin RLS. FORCE además de ENABLE porque el dueño está exento por default y las
-- migraciones corren como dueño; sin él los tests pasarían sobre policies que en
-- producción no aplican igual. Un superusuario saltea RLS pase lo que pase, así
-- que la app se conecta con un rol que no es ninguna de las dos cosas.
ALTER TABLE athlete ENABLE ROW LEVEL SECURITY;
ALTER TABLE athlete FORCE  ROW LEVEL SECURITY;

-- Dos policies por tabla, una por rol, nunca una sola con OR adentro. Postgres
-- combina las permisivas con OR igual; la diferencia es que cada una arranca
-- chequeando el rol activo, así que nunca son verdaderas las dos. Un
-- `USING (coach OR atleta)` deja a la persona con los dos roles viendo todo
-- desde cualquiera, y no se nota leyendo el diff.
--
-- WITH CHECK en todas, no sólo en logged_set: USING no decide si un INSERT se
-- permite —eso lo hace WITH CHECK—, y
-- una tabla cuya policy no tiene WITH CHECK rechaza toda escritura.
CREATE POLICY athlete_as_coach ON athlete
    USING (app_active_role() = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id AND c.user_id = app_current_user_id()))
    WITH CHECK (app_active_role() = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id AND c.user_id = app_current_user_id()));

CREATE POLICY athlete_as_athlete ON athlete
    USING      (app_active_role() = 'athlete' AND athlete.user_id = app_current_user_id())
    WITH CHECK (app_active_role() = 'athlete' AND athlete.user_id = app_current_user_id());

-- El caso donde WITH CHECK hace trabajo propio y no copia al USING: el criterio
-- de aceptación 4. Sin el segundo EXISTS, el atleta manda su propio athlete_id
-- con un prescribed_set_id ajeno y la fila entra — los dos predicados de "es
-- mío" pasan por separado, falta que se correspondan entre sí.
CREATE POLICY logged_set_as_athlete ON logged_set
    USING (app_active_role() = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id AND a.user_id = app_current_user_id()))
    WITH CHECK (app_active_role() = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id AND a.user_id = app_current_user_id())
           AND app_athlete_ve_prescribed_set(logged_set.prescribed_set_id));
