\set ON_ERROR_STOP 1

-- Cada bloque desarma UNA decision del plan y muestra que sin ella hay fuga.
-- Si alguno de estos dice "SIN FUGA", esa decision no hacia falta.

\echo ''
\echo '########## A. Sin el segundo EXISTS del WITH CHECK (o sea, sin T-008b) ##########'
DROP POLICY logged_set_as_athlete ON logged_set;
CREATE POLICY logged_set_as_athlete ON logged_set
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id
                         AND a.user_id = app_current_user_id()))
    WITH CHECK (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id
                         AND a.user_id = app_current_user_id()));
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-d';
SET LOCAL app.active_role = 'athlete';
DO $$
BEGIN
    INSERT INTO logged_set (prescribed_set_id, athlete_id, reps, load_kg)
    VALUES ('00000000-0000-0000-0000-00000000ac50',
            '00000000-0000-0000-0000-00000000ad01', 10, 60);
    RAISE NOTICE 'FUGA CONFIRMADA: D escribio sobre una serie prescrita a C.';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'SIN FUGA: algo mas lo tapaba; T-008b seria innecesaria';
END $$;
ROLLBACK;

\echo ''
\echo '########## B. Una sola policy con OR en vez de dos por rol ##########'
DROP POLICY athlete_as_coach ON athlete;
DROP POLICY athlete_as_athlete ON athlete;
CREATE POLICY athlete_or ON athlete
    USING (EXISTS (SELECT 1 FROM coach c
                   WHERE c.id = athlete.coach_id
                     AND c.user_id = app_current_user_id())
           OR athlete.user_id = app_current_user_id());
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-c';
SET LOCAL app.active_role = 'athlete';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids = 'C segun A' THEN
        RAISE NOTICE 'SIN FUGA: el OR alcanzaba';
    ELSE
        RAISE NOTICE 'FUGA CONFIRMADA: C con rol athlete ve [%]', ids;
    END IF;
END $$;
ROLLBACK;

\echo ''
\echo '########## C. Policy de app_user usando la funcion (recursion) ##########'
DROP POLICY app_user_self ON app_user;
CREATE POLICY app_user_recursiva ON app_user
    USING (id = app_current_user_id());
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM app_user;
    RAISE NOTICE 'SIN PROBLEMA: devolvio % filas, no hubo recursion', n;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'CONFIRMADO [%]: %', SQLSTATE, SQLERRM;
END $$;
ROLLBACK;

\echo ''
\echo '########## D. ENABLE sin FORCE, consultando como DUENO de las tablas ##########'
DROP POLICY athlete_or ON athlete;
CREATE POLICY athlete_as_coach ON athlete
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id
                         AND c.user_id = app_current_user_id()));
ALTER TABLE athlete NO FORCE ROW LEVEL SECURITY;
-- El dueno de las tablas en esta base es `coach`, que ademas es superusuario del
-- cluster. Un superusuario saltea RLS SIEMPRE, con FORCE o sin el, asi que este
-- bloque muestra el riesgo combinado: correr la app con el rol equivocado.
BEGIN;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    RAISE NOTICE 'Como dueno/superusuario, con contexto de A, ve: [%]', ids;
END $$;
ROLLBACK;
