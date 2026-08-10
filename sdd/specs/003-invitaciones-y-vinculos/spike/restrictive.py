"""Spike: cómo se bloquea la escritura sobre un vínculo archivado sin un `if` por endpoint.

Reproduce las dos mediciones sobre las que se apoya la sección 4 del plan:

1. Una policy `FOR ALL` con `WITH CHECK` **no** bloquea `DELETE`. Es el espejo de
   la lección de la 001, donde `USING` no cubría `INSERT`.
2. Una policy permisiva `FOR ALL` más policies `RESTRICTIVE` por comando sí lo
   hace, y deja la lectura intacta.

Está en Python y no en SQL como el spike de la 001 por una razón concreta: cada
caso necesita su propia transacción con datos frescos. La primera versión de esto
corrió los casos en una sola transacción y el `DELETE` borró la fila que el
`UPDATE` siguiente iba a medir, así que el `UPDATE` dio 0 filas por estar vacía la
tabla y no por la policy. El resultado parecía correcto y no probaba nada.

Y corre con `SET LOCAL ROLE coachapp_app` por una razón todavía más importante:
el rol `coach` de desarrollo **es superusuario**, y un superusuario ignora RLS
incluso con `FORCE ROW LEVEL SECURITY`. Medido como dueño, este spike reporta que
no hay ninguna policy y lo hace sin fallar.

    DATABASE_URL=postgresql+psycopg://coach:coach@localhost:5433/coachapp \
        python sdd/specs/003-invitaciones-y-vinculos/spike/restrictive.py
"""

from __future__ import annotations

import os
import sys

import sqlalchemy as sa

SETUP = """
    CREATE TABLE spike_v (id int primary key, archivado bool not null);
    INSERT INTO spike_v VALUES (1, true), (2, false);
    ALTER TABLE spike_v ENABLE ROW LEVEL SECURITY;
    ALTER TABLE spike_v FORCE ROW LEVEL SECURITY;
    GRANT SELECT, INSERT, UPDATE, DELETE ON spike_v TO coachapp_app;
"""

FOR_ALL = "CREATE POLICY p ON spike_v FOR ALL USING (true) WITH CHECK (NOT archivado);"

RESTRICTIVE = """
    CREATE POLICY p ON spike_v FOR ALL USING (true) WITH CHECK (true);
    CREATE POLICY p_del ON spike_v AS RESTRICTIVE FOR DELETE USING (NOT archivado);
    CREATE POLICY p_upd ON spike_v AS RESTRICTIVE FOR UPDATE USING (NOT archivado);
    CREATE POLICY p_ins ON spike_v AS RESTRICTIVE FOR INSERT WITH CHECK (NOT archivado);
"""


def main() -> int:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("Falta DATABASE_URL (el DSN del dueño: crea tablas y policies).", file=sys.stderr)
        return 2
    engine = sa.create_engine(dsn)

    with engine.connect() as conn:
        if conn.execute(sa.text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")).scalar():
            print("Aviso: el DSN es de un superusuario. El spike cambia de rol para medir.")

    def caso(titulo: str, policies: str, accion: str) -> None:
        with engine.connect() as conn:
            conn.execute(sa.text(SETUP))
            conn.execute(sa.text(policies))
            conn.execute(sa.text("SET LOCAL ROLE coachapp_app"))
            try:
                filas = conn.execute(sa.text(accion)).rowcount
                print(f"  {titulo:<34} {filas} fila(s)")
            except sa.exc.DBAPIError as exc:
                print(f"  {titulo:<34} RECHAZADO ({type(exc.orig).__name__})")
            conn.rollback()

    def leer(titulo: str, policies: str) -> None:
        caso(titulo, policies, "SELECT * FROM spike_v WHERE archivado")

    print("\n1. FOR ALL con WITH CHECK")
    leer("SELECT sobre archivada", FOR_ALL)
    caso("UPDATE sobre archivada", FOR_ALL, "UPDATE spike_v SET id=99 WHERE archivado")
    caso("DELETE sobre archivada", FOR_ALL, "DELETE FROM spike_v WHERE archivado")
    print("  -> el DELETE pasa: WITH CHECK no cubre DELETE.")

    print("\n2. Permisiva + RESTRICTIVE por comando")
    leer("SELECT sobre archivada", RESTRICTIVE)
    caso("UPDATE sobre archivada", RESTRICTIVE, "UPDATE spike_v SET id=99 WHERE archivado")
    caso("DELETE sobre archivada", RESTRICTIVE, "DELETE FROM spike_v WHERE archivado")
    caso("INSERT de fila archivada", RESTRICTIVE, "INSERT INTO spike_v VALUES (3, true)")
    caso("DELETE sobre la viva", RESTRICTIVE, "DELETE FROM spike_v WHERE NOT archivado")
    caso("UPDATE sobre la viva", RESTRICTIVE, "UPDATE spike_v SET id=98 WHERE NOT archivado")
    print("  -> lectura intacta, escritura bloqueada, lo vivo se sigue tocando.")
    print("  -> el INSERT tira error; el UPDATE y el DELETE devuelven 0 filas en silencio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
