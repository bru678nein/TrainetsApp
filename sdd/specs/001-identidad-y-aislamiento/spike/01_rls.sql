-- Spike de T-008: el DDL de la seccion 4 del plan, aplicado tal cual.
-- Base desechable. No es la migracion.

DROP ROLE IF EXISTS app_rls;
CREATE ROLE app_rls NOLOGIN;
GRANT USAGE ON SCHEMA public TO app_rls;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rls;

CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT u.id FROM app_user u
    WHERE u.auth_user_id = current_setting('app.current_auth_user_id')
$$;

-- movement_pattern queda sin RLS: referencia pura.
ALTER TABLE app_user       ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_user       FORCE  ROW LEVEL SECURITY;
ALTER TABLE coach          ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach          FORCE  ROW LEVEL SECURITY;
ALTER TABLE athlete        ENABLE ROW LEVEL SECURITY;
ALTER TABLE athlete        FORCE  ROW LEVEL SECURITY;
ALTER TABLE exercise       ENABLE ROW LEVEL SECURITY;
ALTER TABLE exercise       FORCE  ROW LEVEL SECURITY;
ALTER TABLE program        ENABLE ROW LEVEL SECURITY;
ALTER TABLE program        FORCE  ROW LEVEL SECURITY;
ALTER TABLE mesocycle      ENABLE ROW LEVEL SECURITY;
ALTER TABLE mesocycle      FORCE  ROW LEVEL SECURITY;
ALTER TABLE session        ENABLE ROW LEVEL SECURITY;
ALTER TABLE session        FORCE  ROW LEVEL SECURITY;
ALTER TABLE prescription   ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescription   FORCE  ROW LEVEL SECURITY;
ALTER TABLE prescribed_set ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescribed_set FORCE  ROW LEVEL SECURITY;
ALTER TABLE logged_set     ENABLE ROW LEVEL SECURITY;
ALTER TABLE logged_set     FORCE  ROW LEVEL SECURITY;

-- app_user: directo contra auth_user_id, sin la funcion (se llamaria a si misma).
CREATE POLICY app_user_self ON app_user
    USING      (auth_user_id = current_setting('app.current_auth_user_id'))
    WITH CHECK (auth_user_id = current_setting('app.current_auth_user_id'));

CREATE POLICY coach_as_coach ON coach
    USING (current_setting('app.active_role') = 'coach'
           AND coach.user_id = app_current_user_id());

CREATE POLICY athlete_as_coach ON athlete
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY athlete_as_athlete ON athlete
    USING (current_setting('app.active_role') = 'athlete'
           AND athlete.user_id = app_current_user_id());

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

CREATE POLICY program_as_coach ON program
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = program.coach_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY program_as_athlete ON program
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = program.athlete_id
                         AND a.user_id = app_current_user_id()));

CREATE POLICY mesocycle_as_coach ON mesocycle
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM program p JOIN coach c ON c.id = p.coach_id
                       WHERE p.id = mesocycle.program_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY mesocycle_as_athlete ON mesocycle
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM program p JOIN athlete a ON a.id = p.athlete_id
                       WHERE p.id = mesocycle.program_id
                         AND a.user_id = app_current_user_id()));

CREATE POLICY session_as_coach ON session
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM mesocycle m
                       JOIN program p ON p.id = m.program_id
                       JOIN coach   c ON c.id = p.coach_id
                       WHERE m.id = session.mesocycle_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY session_as_athlete ON session
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM mesocycle m
                       JOIN program p ON p.id = m.program_id
                       JOIN athlete a ON a.id = p.athlete_id
                       WHERE m.id = session.mesocycle_id
                         AND a.user_id = app_current_user_id()));

CREATE POLICY prescription_as_coach ON prescription
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM session s
                       JOIN mesocycle m ON m.id = s.mesocycle_id
                       JOIN program   p ON p.id = m.program_id
                       JOIN coach     c ON c.id = p.coach_id
                       WHERE s.id = prescription.session_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY prescription_as_athlete ON prescription
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM session s
                       JOIN mesocycle m ON m.id = s.mesocycle_id
                       JOIN program   p ON p.id = m.program_id
                       JOIN athlete   a ON a.id = p.athlete_id
                       WHERE s.id = prescription.session_id
                         AND a.user_id = app_current_user_id()));

CREATE POLICY prescribed_set_as_coach ON prescribed_set
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM prescription pr
                       JOIN session   s ON s.id = pr.session_id
                       JOIN mesocycle m ON m.id = s.mesocycle_id
                       JOIN program   p ON p.id = m.program_id
                       JOIN coach     c ON c.id = p.coach_id
                       WHERE pr.id = prescribed_set.prescription_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY prescribed_set_as_athlete ON prescribed_set
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM prescription pr
                       JOIN session   s ON s.id = pr.session_id
                       JOIN mesocycle m ON m.id = s.mesocycle_id
                       JOIN program   p ON p.id = m.program_id
                       JOIN athlete   a ON a.id = p.athlete_id
                       WHERE pr.id = prescribed_set.prescription_id
                         AND a.user_id = app_current_user_id()));

CREATE POLICY logged_set_as_coach ON logged_set
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM prescribed_set ps
                       JOIN prescription pr ON pr.id = ps.prescription_id
                       JOIN session      s  ON s.id  = pr.session_id
                       JOIN mesocycle    m  ON m.id  = s.mesocycle_id
                       JOIN program      p  ON p.id  = m.program_id
                       JOIN coach        c  ON c.id  = p.coach_id
                       WHERE ps.id = logged_set.prescribed_set_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY logged_set_as_athlete ON logged_set
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id
                         AND a.user_id = app_current_user_id()))
    WITH CHECK (
        current_setting('app.active_role') = 'athlete'
        AND EXISTS (SELECT 1 FROM athlete a
                    WHERE a.id = logged_set.athlete_id
                      AND a.user_id = app_current_user_id())
        AND EXISTS (SELECT 1
                    FROM prescribed_set ps
                    JOIN prescription pr ON pr.id = ps.prescription_id
                    JOIN session      s  ON s.id  = pr.session_id
                    JOIN mesocycle    m  ON m.id  = s.mesocycle_id
                    JOIN program      p  ON p.id  = m.program_id
                    WHERE ps.id = logged_set.prescribed_set_id
                      AND p.athlete_id = logged_set.athlete_id));
