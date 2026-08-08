\set ON_ERROR_STOP 1

\echo ''
\echo '##### B-bis. El OR, cuando la policy de `coach` no filtra por rol #####'
\echo '      (una policy razonable por si sola: "el coach se ve a si mismo")'
DROP POLICY coach_as_coach ON coach;
CREATE POLICY coach_self ON coach USING (coach.user_id = app_current_user_id());
ALTER TABLE athlete FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS athlete_as_coach ON athlete;
DROP POLICY IF EXISTS athlete_as_athlete ON athlete;
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
        RAISE NOTICE 'SIN FUGA';
    ELSE
        RAISE NOTICE 'FUGA CONFIRMADA: C con rol athlete ve [%]', ids;
    END IF;
END $$;
ROLLBACK;

\echo ''
\echo '##### B-ter. Las dos policies por rol, con la MISMA policy de coach sin gate #####'
DROP POLICY athlete_or ON athlete;
CREATE POLICY athlete_as_coach ON athlete
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id
                         AND c.user_id = app_current_user_id()));
CREATE POLICY athlete_as_athlete ON athlete
    USING (current_setting('app.active_role') = 'athlete'
           AND athlete.user_id = app_current_user_id());
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-c';
SET LOCAL app.active_role = 'athlete';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids = 'C segun A' THEN
        RAISE NOTICE 'AGUANTA: [%] — el gate por rol no depende de la policy vecina', ids;
    ELSE
        RAISE NOTICE 'FUGA: [%]', ids;
    END IF;
END $$;
ROLLBACK;

\echo ''
\echo '##### E. FORCE, con un dueno que NO es superusuario #####'
ALTER TABLE athlete OWNER TO app_rls;
ALTER TABLE athlete NO FORCE ROW LEVEL SECURITY;
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    RAISE NOTICE 'ENABLE sin FORCE, como dueno: ve [%]', ids;
END $$;
ROLLBACK;

ALTER TABLE athlete FORCE ROW LEVEL SECURITY;
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    RAISE NOTICE 'ENABLE + FORCE, como dueno: ve [%]', ids;
END $$;
ROLLBACK;
