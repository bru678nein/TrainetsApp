"""Una invitación no revive un vínculo que el entrenador cerró

La spec dice que archivar invalida la invitación pendiente. Faltaba, y lo
encontró el test del criterio 11: con el vínculo archivado, aceptar seguía
asociando.

Se resuelve en la función y no revocando al archivar, y la diferencia importa.
Revocar al archivar protege mientras archivar pase por ese único endpoint;
chequear acá protege sin importar cómo se llegó al estado — un script de
mantenimiento, una migración futura, o un segundo camino que todavía no existe.
La garantía no depende de que nadie más aprenda a archivar.

`vinculo_archivado` es un sexto resultado y no se mezcla con `inexistente`,
porque las dos situaciones piden acciones distintas: una se arregla pidiendo otro
link, la otra reactivando el vínculo, y sólo el entrenador puede hacer la segunda.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "coachapp_app"

_CHEQUEO = """
    IF ficha.estado = 'archivado' THEN
        RETURN 'vinculo_archivado';
    END IF;
"""


def _funcion(con_chequeo: bool) -> str:
    extra = _CHEQUEO if con_chequeo else ""
    return f"""
CREATE OR REPLACE FUNCTION app_aceptar_invitacion(p_token_hash bytea, p_user_id uuid)
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

    IF NOT FOUND OR inv.revoked_at IS NOT NULL THEN
        RETURN 'inexistente';
    END IF;

    IF inv.accepted_at IS NOT NULL THEN
        RETURN 'usada';
    END IF;

    IF inv.expires_at <= now() THEN
        RETURN 'vencida';
    END IF;

    SELECT * INTO ficha FROM athlete WHERE id = inv.athlete_id;
    IF NOT FOUND THEN
        RETURN 'inexistente';
    END IF;
{extra}
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
    op.execute(_funcion(con_chequeo=True))
    firma = "app_aceptar_invitacion(bytea, uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(_funcion(con_chequeo=False))
    firma = "app_aceptar_invitacion(bytea, uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {firma} TO {APP_ROLE}")
