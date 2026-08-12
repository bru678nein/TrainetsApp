"""Aceptar una invitación: el único lugar que cruza el límite del tenant

Quien acepta tiene identidad —viene con un token del proveedor— pero **ningún
vínculo con la ficha que va a aceptar**. No existe todavía. Así que no hay
contexto de tenant que setear, y ninguna policy lo dejaría escribir.

Por eso esto es una función `SECURITY DEFINER` y no un endpoint con una sesión
sin RLS. La alternativa reparte el permiso de cruzar el límite por el código, y
el día que alguien agregue una consulta al lado la hace con el mismo privilegio
sin notarlo. Acá hay exactamente un lugar auditable, y su cuerpo es la lista de
verificaciones.

Recibe un `app_user.id` ya resuelto y no el `sub` del token. Crear la identidad
necesita el email y el nombre, que viven en el token y se leen en Python — es el
mismo corte que ya usa el alta de entrenador. Esta función hace lo que tiene que
ser atómico y nada más.

Devuelve **cuál** de los casos ocurrió y no un booleano, para distinguir
un link vencido de uno inválido, porque esa distinción ayuda a la persona
correcta y no le sirve de nada a un atacante — un link vencido ya no vale.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

FUNCION = """
CREATE FUNCTION app_aceptar_invitacion(p_token_hash bytea, p_user_id uuid)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    inv        invitation%ROWTYPE;
    ficha      athlete%ROWTYPE;
    duplicada  uuid;
BEGIN
    SELECT * INTO inv FROM invitation WHERE token_hash = p_token_hash;

    -- Revocada e inexistente contestan lo mismo a propósito. Que un link
    -- regenerado diga "esto existió" le informa a quien lo tenga y no ayuda a
    -- quien lo recibió: para esa persona, pedir uno nuevo es la misma acción.
    IF NOT FOUND OR inv.revoked_at IS NOT NULL THEN
        RETURN 'inexistente';
    END IF;

    IF inv.accepted_at IS NOT NULL THEN
        RETURN 'usada';
    END IF;

    -- `now()` es el arranque de la transacción, no el reloj de la aplicación.
    -- Comparar contra una hora que manda el cliente sería dejarle elegir si su
    -- link venció.
    IF inv.expires_at <= now() THEN
        RETURN 'vencida';
    END IF;

    SELECT * INTO ficha FROM athlete WHERE id = inv.athlete_id;
    IF NOT FOUND THEN
        RETURN 'inexistente';
    END IF;

    -- Dos formas del mismo "esto no te conecta con nadie nuevo": que la ficha ya
    -- tenga cuenta, o que la persona ya sea atleta de ese entrenador por otra
    -- ficha. La segunda pasa cuando el entrenador crea la ficha dos veces, y el
    -- índice `athlete_coach_user_uq` la rechazaría igual — con un error de
    -- unicidad que no le explica nada a quien está del otro lado.
    IF ficha.user_id IS NOT NULL AND ficha.user_id <> p_user_id THEN
        RETURN 'ya_vinculado';
    END IF;

    SELECT a.id INTO duplicada
    FROM athlete a
    WHERE a.coach_id = ficha.coach_id AND a.user_id = p_user_id AND a.id <> ficha.id;
    IF FOUND THEN
        RETURN 'ya_vinculado';
    END IF;

    UPDATE athlete SET user_id = p_user_id WHERE id = ficha.id;
    UPDATE invitation
       SET accepted_at = now(), accepted_by = p_user_id
     WHERE id = inv.id;

    RETURN 'aceptada';
END
$$
"""


def upgrade() -> None:
    op.execute(FUNCION)
    firma = "app_aceptar_invitacion(bytea, uuid)"
    # Revocada de PUBLIC antes de otorgar: una SECURITY DEFINER es ejecutable por
    # cualquiera por default, y ésta escribe sobre la ficha de otra persona.
    op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_aceptar_invitacion(bytea, uuid)")
