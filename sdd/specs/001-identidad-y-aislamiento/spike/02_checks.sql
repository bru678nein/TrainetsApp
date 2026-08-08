\set ON_ERROR_STOP 1

\echo '=== 1. Sesion sin contexto: error, no cero filas ==='
BEGIN;
SET ROLE app_rls;
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM athlete;
    RAISE EXCEPTION 'FALLA: devolvio % filas en vez de error', n;
EXCEPTION WHEN undefined_object THEN
    RAISE NOTICE 'OK: %', SQLERRM;
END $$;
ROLLBACK;

\echo '=== 2. Coach A ve sus 2 atletas y nada mas ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids IS DISTINCT FROM 'C segun A, D segun A' THEN
        RAISE EXCEPTION 'FALLA: A ve [%]', ids;
    END IF;
    RAISE NOTICE 'OK: A ve [%]', ids;
END $$;
ROLLBACK;

\echo '=== 3. Coach A pidiendo por id el atleta de B: cero filas ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE n int;
BEGIN
    SELECT count(*) INTO n FROM athlete
     WHERE id = '00000000-0000-0000-0000-00000000bd01';
    IF n <> 0 THEN RAISE EXCEPTION 'FALLA: A ve el atleta de B'; END IF;
    RAISE NOTICE 'OK: id ajeno responde igual que uno inexistente';
END $$;
ROLLBACK;

\echo '=== 4. Persona D (atleta de A y de B) ve sus dos fichas ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-d';
SET LOCAL app.active_role = 'athlete';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids IS DISTINCT FROM 'D segun A, D segun B' THEN
        RAISE EXCEPTION 'FALLA: D ve [%]', ids;
    END IF;
    RAISE NOTICE 'OK: D ve [%] y nada del espacio de A ni de B', ids;
END $$;
ROLLBACK;

\echo '=== 5. RIESGO 2 DE LA SPEC: C es coach Y atleta de A ==='
\echo '     Con rol athlete NO puede ver su propio espacio de entrenador.'
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-c';
SET LOCAL app.active_role = 'athlete';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids IS DISTINCT FROM 'C segun A' THEN
        RAISE EXCEPTION 'FALLA: C como atleta ve [%] — se filtro su espacio de coach', ids;
    END IF;
    RAISE NOTICE 'OK: como atleta ve solo [%]', ids;
END $$;
ROLLBACK;

BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-c';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(full_name, ', ' ORDER BY full_name) INTO ids FROM athlete;
    IF ids IS DISTINCT FROM 'Ficha sin cuenta de C' THEN
        RAISE EXCEPTION 'FALLA: C como coach ve [%]', ids;
    END IF;
    RAISE NOTICE 'OK: la misma persona, con rol coach, ve solo [%]', ids;
END $$;
ROLLBACK;

\echo '=== 6. Catalogo global visible, el de B no ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-a';
SET LOCAL app.active_role = 'coach';
DO $$
DECLARE ids text;
BEGIN
    SELECT string_agg(name, ', ' ORDER BY name) INTO ids FROM exercise;
    IF ids IS DISTINCT FROM 'Press banca (global), Press de A' THEN
        RAISE EXCEPTION 'FALLA: A ve [%]', ids;
    END IF;
    RAISE NOTICE 'OK: A ve [%]', ids;
END $$;
ROLLBACK;

\echo '=== 7. logged_set legitimo: D registra SU serie ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-d';
SET LOCAL app.active_role = 'athlete';
DO $$
BEGIN
    INSERT INTO logged_set (prescribed_set_id, athlete_id, reps, load_kg)
    VALUES ('00000000-0000-0000-0000-00000000ad50',
            '00000000-0000-0000-0000-00000000ad01', 10, 60);
    RAISE NOTICE 'OK: la escritura propia entra';
END $$;
ROLLBACK;

\echo '=== 8. CRITERIO 4: D firma con SU athlete_id una serie prescrita a C ==='
BEGIN;
SET ROLE app_rls;
SET LOCAL app.current_auth_user_id = 'sub-d';
SET LOCAL app.active_role = 'athlete';
DO $$
BEGIN
    INSERT INTO logged_set (prescribed_set_id, athlete_id, reps, load_kg)
    VALUES ('00000000-0000-0000-0000-00000000ac50',   -- serie de C
            '00000000-0000-0000-0000-00000000ad01',   -- ficha de D
            10, 60);
    RAISE EXCEPTION 'FALLA: entro una serie ajena firmada como propia';
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'OK: rechazado por WITH CHECK — %', SQLERRM;
END $$;
ROLLBACK;
