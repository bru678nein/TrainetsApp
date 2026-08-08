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
--  El RLS del final todavía NO está aplicado: entra con la tarea T-008 de la
--  feature 001, junto con la resolución de tenant en la capa HTTP.
--  Ver sdd/specs/001-identidad-y-aislamiento/.
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
-- entrenador: la feature 003 archiva el vínculo anterior en vez de borrarlo, así
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
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX athlete_coach_idx ON athlete (coach_id) WHERE is_active;

-- Una persona es a lo sumo un atleta de un entrenador dado, pero puede serlo de
-- varios entrenadores. Parcial y no UNIQUE normal: `user_id` es NULL en toda
-- ficha sin cuenta y en Postgres los NULL no colisionan entre sí, así que un
-- UNIQUE común parecería cubrir esto y no cubriría nada.
CREATE UNIQUE INDEX athlete_coach_user_uq
    ON athlete (coach_id, user_id) WHERE user_id IS NOT NULL;

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
-- El motivo es el artículo I de la constitución. El dominio calcula e1RM sin
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
-- Aislamiento por tenant con RLS. TODAVÍA NO APLICADO: entra con la tarea T-008
-- de la feature 001, junto con la resolución de tenant en la capa HTTP.
-- Activarlo antes dejaría la app viendo cero filas.
--
-- Lo de abajo es el bosquejo, no el DDL final. Cinco cosas que la versión
-- anterior de este archivo daba por sentadas y son falsas:
--
-- 1. Sólo `athlete`, `program` y `exercise` tienen `coach_id`. Las otras cinco
--    llegan a su entrenador por cadena de claves foráneas, así que su policy
--    sube con EXISTS. El camino de cada tabla está en la sección 4 del plan de
--    la 001. Denormalizar `coach_id` en todas es una opción con su costo: bajo
--    RLS una copia desincronizada no es un dato feo, es una filtración.
--
-- 2. `ENABLE` no alcanza: hace falta `FORCE`, porque el dueño de la tabla
--    saltea RLS por default y las migraciones corren como dueño. Sin `FORCE`,
--    los tests pasarían sobre policies que en producción no aplican igual.
--
-- 3. La app no se conecta como dueña de las tablas. Hace falta un rol sin
--    privilegios especiales (T-007).
--
-- 4. El rol activo cambia el predicado, así que cada tabla lleva DOS policies,
--    una por rol, y no una sola con un `OR` adentro. Postgres combina las
--    policies permisivas con OR igual; la diferencia es que el chequeo de rol
--    garantiza que nunca sean verdaderas las dos a la vez. Un `USING (coach OR
--    atleta)` deja a la persona con los dos roles viendo todo desde cualquiera
--    de los dos, y eso no se ve leyendo el diff.
--
-- 5. `USING` no se aplica a un INSERT: una fila que todavía no existe no se
--    puede filtrar. Lo que gobierna la escritura es `WITH CHECK`, y ahí vive el
--    criterio de aceptación 4 (un atleta no registra una serie prescrita a
--    otro). Con `USING` solo, ese criterio no se cumple aunque los tests de
--    lectura estén todos verdes.
--
-- El `current_setting` va SIN el segundo argumento a propósito: una sesión sin
-- contexto tiene que dar error, no cero filas. Con `missing_ok = true` un
-- `SET LOCAL` olvidado se ve igual que "este usuario no tiene datos" y puede
-- vivir meses.
-- -----------------------------------------------------------------------------

-- El contrato de la sesión: dos variables, siempre las dos, ninguna con default.
--
--   app.current_auth_user_id  text  -- el `sub` del JWT, verificado
--   app.active_role           text  -- 'coach' | 'athlete', del header Active-Role
--
-- `active_role` y no `current_role`: CURRENT_ROLE es palabra reservada, y
-- `SET LOCAL app.current_role = 'coach'` es error de sintaxis aun con el
-- prefijo. La trampa es que current_setting('app.current_role') SI compila
-- adentro de la policy, porque ahi es un literal de texto: el DDL entra sin
-- quejarse y la app revienta recien en runtime, al setear el contexto.
--
-- La variable lleva el `sub` y no `app_user.id`, que parece un rodeo y evita un
-- punto muerto: traducir uno en otro exige leer `app_user`, y esa lectura pasa
-- ANTES de que exista contexto. Con RLS forzado sobre `app_user` tira error; sin
-- RLS sobre `app_user`, cualquier entrenador lee el email de todas las personas
-- del sistema. Con el `sub`, el SET LOCAL es función pura del token y no toca la
-- base: no hay ningún instante con sesión abierta y sin contexto.
--
-- Corolario de tipo: es `text`, no `uuid`. Castearla con ::uuid es un error.
CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT u.id FROM app_user u
    WHERE u.auth_user_id = current_setting('app.current_auth_user_id')
$$;
-- STABLE y no IMMUTABLE: el valor no cambia dentro de una transacción, pero
-- depende del estado de la sesión. IMMUTABLE dejaría al planner constant-foldear
-- el resultado entre transacciones, que es la optimización que lo convierte en
-- una filtración.

-- Se habilita en toda tabla que abajo lleve policy. Una CREATE POLICY sobre una
-- tabla sin ENABLE se aplica sin error y no filtra nada: la policy queda escrita,
-- se lee en el diff como protección, y no protege. Por eso las dos listas —lo
-- que se habilita y lo que lleva policy— tienen que coincidir a ojo.
ALTER TABLE app_user   ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user   FORCE  ROW LEVEL SECURITY;
ALTER TABLE athlete    ENABLE ROW LEVEL SECURITY;
ALTER TABLE athlete    FORCE  ROW LEVEL SECURITY;
ALTER TABLE exercise   ENABLE ROW LEVEL SECURITY;
ALTER TABLE exercise   FORCE  ROW LEVEL SECURITY;
ALTER TABLE logged_set ENABLE ROW LEVEL SECURITY;
ALTER TABLE logged_set FORCE  ROW LEVEL SECURITY;
-- ...y lo mismo para coach, program, mesocycle, session, prescription y
-- prescribed_set, cuyas policies no se transcriben acá porque repiten la misma
-- forma que `logged_set`. El DDL completo, con las 18 policies, está en
-- sdd/specs/001-identidad-y-aislamiento/spike/01_rls.sql, que es el que se
-- corrió de verdad. `movement_pattern` es referencia pura y queda sin RLS.

-- `app_user` no puede usar app_current_user_id(): se llamaría a sí misma. El
-- detector de recursión de Postgres no lo agarra —mira referencias directas a la
-- propia tabla, y acá pasa por una función—, así que la consulta se va de pila y
-- muere con "stack depth limit exceeded" (54001), un error que ni menciona RLS.
-- Va directo contra auth_user_id.
--
-- Una persona sólo se ve a sí misma, en los dos roles. El entrenador no lee la
-- identidad de sus atletas porque no la necesita: full_name y email viven en
-- `athlete`, cargados a mano por él. La feature 003 va a tener que abrir algo
-- acá, y conviene que sea una decisión de esa feature.
--
-- El WITH CHECK es lo que hace segura la T-011: en el primer login la fila no
-- existe, y la policy deja crear exactamente una —la propia— sin ningún `if` en
-- la aplicación.
CREATE POLICY app_user_self ON app_user
    USING      (auth_user_id = current_setting('app.current_auth_user_id'))
    WITH CHECK (auth_user_id = current_setting('app.current_auth_user_id'));

-- Tabla llana, los dos roles. El entrenador llega por coach_id; el atleta, por
-- su propia identidad.
CREATE POLICY athlete_as_coach ON athlete
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY athlete_as_athlete ON athlete
    USING (current_setting('app.active_role') = 'athlete'
           AND athlete.user_id = app_current_user_id());

-- Tabla profunda: `logged_set` no tiene coach_id y sube cinco niveles. El EXISTS
-- recorre claves foráneas ya indexadas.
--
-- La cadena se escribe entera aunque Postgres la acorte: un EXISTS contra
-- `program` ya viene filtrado por la policy de `program`, porque RLS se aplica
-- también a las subconsultas de una policy. No se aprovecha — la policy pasaría
-- a leerse como "cualquier programa" y su corrección dependería de otra policy
-- que `\dp` no muestra.
CREATE POLICY logged_set_as_coach ON logged_set
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (
               SELECT 1
               FROM prescribed_set ps
               JOIN prescription pr ON pr.id = ps.prescription_id
               JOIN session      s  ON s.id  = pr.session_id
               JOIN mesocycle    m  ON m.id  = s.mesocycle_id
               JOIN program      p  ON p.id  = m.program_id
               JOIN coach        c  ON c.id  = p.coach_id
               WHERE ps.id = logged_set.prescribed_set_id
                 AND c.user_id = app_current_user_id()));

-- La única tabla que el atleta escribe, y por eso la única donde el WITH CHECK
-- hace trabajo real.
CREATE POLICY logged_set_as_athlete ON logged_set
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id
                         AND a.user_id = app_current_user_id()))
    WITH CHECK (
        current_setting('app.active_role') = 'athlete'
        -- la fila es mía...
        AND EXISTS (SELECT 1 FROM athlete a
                    WHERE a.id = logged_set.athlete_id
                      AND a.user_id = app_current_user_id())
        -- ...y la serie que estoy registrando me fue prescrita a mí.
        -- Este segundo EXISTS es el criterio de aceptación 4 entero: sin él, el
        -- atleta manda su propio athlete_id con un prescribed_set_id ajeno y la
        -- fila entra, porque los dos predicados de "es mío" pasan por separado.
        AND EXISTS (SELECT 1
                    FROM prescribed_set ps
                    JOIN prescription pr ON pr.id = ps.prescription_id
                    JOIN session      s  ON s.id  = pr.session_id
                    JOIN mesocycle    m  ON m.id  = s.mesocycle_id
                    JOIN program      p  ON p.id  = m.program_id
                    WHERE ps.id = logged_set.prescribed_set_id
                      AND p.athlete_id = logged_set.athlete_id));

-- `exercise` es la excepción del catálogo global: coach_id IS NULL tiene que
-- seguir visible para todos, y el atleta ve además los del entrenador que lo
-- entrena, porque son los que aparecen en su sesión.
CREATE POLICY exercise_as_coach ON exercise
    USING (current_setting('app.active_role') = 'coach'
           AND (exercise.coach_id IS NULL
                OR EXISTS (SELECT 1 FROM coach c
                           WHERE c.id = exercise.coach_id
                             AND c.user_id = app_current_user_id())));

CREATE POLICY exercise_as_athlete ON exercise
    USING (current_setting('app.active_role') = 'athlete'
           AND (exercise.coach_id IS NULL
                OR EXISTS (SELECT 1 FROM athlete a
                           WHERE a.coach_id = exercise.coach_id
                             AND a.user_id = app_current_user_id())));
