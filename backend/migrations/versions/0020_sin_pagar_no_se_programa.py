"""Un entrenador sin la suscripción al día no programa

El portón del cobro, y va en el esquema por el mismo motivo que el aislamiento:
un `if` protege el endpoint que lo tiene, la policy protege también al que
alguien escriba mañana. Un cobro que se saltea editando el frontend no es un
cobro.

Reusa la forma de la 0009 —`RESTRICTIVE` por comando de escritura— porque es
literalmente el mismo problema: hay un estado del vínculo bajo el cual no se
escribe, y se lee igual.

Tres decisiones que no son técnicas:

- **`SELECT` no lleva ninguna, y esa ausencia es la feature.** Vencida la
  suscripción se sigue viendo y exportando todo. Un producto que secuestra el
  entrenamiento de personas reales cuando falla una tarjeta no se lo recomienda
  nadie a nadie.

- **Al atleta no lo toca.** Las policies se saltean cuando el rol activo no es
  `coach`, así que `logged_set` sigue escribiéndose: el atleta no dejó de pagar
  nada y su entrenamiento no se interrumpe. La presión cae sobre quien decide,
  no sobre quien entrena. Comercialmente también es mejor: los datos siguen
  entrando y el día que se regulariza está todo.

- **Una fecha y no un booleano.** `pago_hasta` resuelve gratis los tres casos
  molestos: la prueba inicial, el pago que falló y está reintentando —hay margen
  antes de cortar— y el reembolso. Con un `activo boolean` cada uno es un caso
  especial decidido a las apuradas.

`referencia_externa` guarda el identificador de la suscripción del proveedor, sea
cual sea. Nada más del proveedor entra al esquema: quien traduzca su vocabulario
al nuestro es el webhook, y escribe estas dos columnas. Cambiar de proveedor no
toca ninguna policy.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lo que el entrenador produce. El catálogo —`exercise`, `movement_pattern`— no
# entra: sin programas es inerte, y bloquear el renombre de un ejercicio no
# agrega presión, agrega desconcierto.
DEL_ENTRENADOR = (
    "athlete",
    "invitation",
    "program",
    "mesocycle",
    "session",
    "prescription",
    "prescribed_set",
)

COMANDOS = {"INSERT": "check", "UPDATE": "ambas", "DELETE": "using"}


def upgrade() -> None:
    op.execute(
        "ALTER TABLE coach "
        # Treinta días desde el alta, para todos y también para los que ya
        # existen: el default se aplica a las filas actuales al agregar la
        # columna. Es la prueba inicial, y que sea una columna con default y no
        # una regla en el código la vuelve visible en el esquema.
        "ADD COLUMN pago_hasta timestamptz NOT NULL DEFAULT now() + interval '30 days', "
        "ADD COLUMN referencia_externa varchar(120)"
    )

    # `SECURITY DEFINER` y `search_path` clavado, igual que sus hermanas: la
    # policy corre bajo el rol de la aplicación, que no puede leer `coach` sin
    # pasar por su propia policy, y eso sería recursión.
    op.execute(
        """
        CREATE FUNCTION app_coach_al_dia() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT COALESCE(
                (SELECT c.pago_hasta > now() FROM coach c
                  WHERE c.user_id = app_current_user_id()),
                false)
        $$
        """
    )

    # «O no estás mirando como entrenador, o estás al día». Sin ningún término
    # sobre de quién es la fila, y eso es deliberado.
    #
    # La primera versión llevaba un `NOT (esta fila es tuya)` para no molestar a
    # las filas ajenas. Era innecesario —las permisivas ya impiden tocarlas— y
    # abría el portón: en un `INSERT`, una función que resuelve por el `id` de la
    # fila corre sobre el snapshot anterior a la sentencia, donde esa fila no
    # está, devuelve falso, y el `NOT` lo convierte en «dejalo pasar». Es la
    # trampa que arregló la 0013, esta vez permitiendo en vez de rechazando, y la
    # encontró un test que esperaba un error y no lo recibió.
    #
    # Esta condición no habla de la fila sino de **quien escribe**, así que no
    # necesita mirarla y no puede caer en eso.
    #
    # El término del rol es defensivo y hoy **ningún test lo alcanza**: las
    # únicas siete tablas de esta lista son del entrenador, y las permisivas ya
    # impiden que un atleta escriba en ellas. Verificado por mutación —sacarlo no
    # rompe nada— y se queda igual, para el día que entre acá una tabla que las
    # dos partes escriben. Lo que sí está cubierto es que `logged_set` quede
    # fuera de la lista, que es lo que mantiene al atleta entrenando.
    predicado = "(app_active_role() <> 'coach' OR app_coach_al_dia())"
    for tabla in DEL_ENTRENADOR:
        for comando, forma in COMANDOS.items():
            partes = {
                "check": f"WITH CHECK {predicado}",
                "using": f"USING {predicado}",
                "ambas": f"USING {predicado} WITH CHECK {predicado}",
            }[forma]
            op.execute(
                f"CREATE POLICY {tabla}_suscripcion_al_dia_{comando.lower()} ON {tabla} "
                f"AS RESTRICTIVE FOR {comando} {partes}"
            )


def downgrade() -> None:
    for tabla in DEL_ENTRENADOR:
        for comando in COMANDOS:
            op.execute(
                f"DROP POLICY IF EXISTS {tabla}_suscripcion_al_dia_{comando.lower()} ON {tabla}"
            )
    op.execute("DROP FUNCTION IF EXISTS app_coach_al_dia()")
    op.execute(
        "ALTER TABLE coach "
        "DROP COLUMN IF EXISTS pago_hasta, "
        "DROP COLUMN IF EXISTS referencia_externa"
    )
