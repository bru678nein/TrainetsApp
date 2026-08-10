"""State transitions of the coach-athlete link. Task T-022.

Three states, four actions, and the twelve pairs written out. The table is
explicit rather than derived from rules because the interesting content is in
the rejections, and a rule engine expresses "this is not allowed" as the absence
of a rule — which reads the same as a case nobody thought about.

Pausing and archiving are deliberately different, and this module is where that
survives contact with the code. Pausing hides an athlete from the coach's list
and leaves everything editable; archiving ends the link and freezes the training
history for both sides. The 003 spec separated them because collapsing them
takes away something the coach has today: preparing the programme for somebody
who is coming back from three months off.

No database and no HTTP. The rejection is domain vocabulary; mapping it to a
status code is the adapter's job, the same split as `identity.Rejection`.
"""

from __future__ import annotations

from enum import Enum


class Estado(Enum):
    """What `athlete.estado` holds. The values are what the column stores."""

    ACTIVO = "activo"
    PAUSADO = "pausado"
    ARCHIVADO = "archivado"


class Accion(Enum):
    """What a coach can ask for.

    `REANUDAR` and `REACTIVAR` are not synonyms and the split is the point:
    resuming brings back a paused link, reactivating reopens an archived one.
    Asking for the wrong one gets a rejection that says which one to use.
    """

    PAUSAR = "pausar"
    REANUDAR = "reanudar"
    ARCHIVAR = "archivar"
    REACTIVAR = "reactivar"


class Rechazo(Enum):
    """Why the transition does not happen.

    `VINCULO_ARCHIVADO` exists apart from `YA_ESTA_ASI` on purpose. "That is
    already done" and "the link is over, reopen it first" send whoever is reading
    to two different places, and only the second one names the way out.
    """

    YA_ESTA_ASI = "ya_esta_asi"
    VINCULO_ARCHIVADO = "vinculo_archivado"
    NO_ESTA_ARCHIVADO = "no_esta_archivado"


# The twelve pairs, none missing. Adding a fourth state — the athlete who leaves
# on their own, out of scope today — adds four entries here and the test that
# walks the product of both enums names each one that is still undecided.
_TABLA: dict[tuple[Estado, Accion], Estado | Rechazo] = {
    (Estado.ACTIVO, Accion.PAUSAR): Estado.PAUSADO,
    (Estado.ACTIVO, Accion.REANUDAR): Rechazo.YA_ESTA_ASI,
    (Estado.ACTIVO, Accion.ARCHIVAR): Estado.ARCHIVADO,
    (Estado.ACTIVO, Accion.REACTIVAR): Rechazo.NO_ESTA_ARCHIVADO,
    (Estado.PAUSADO, Accion.PAUSAR): Rechazo.YA_ESTA_ASI,
    (Estado.PAUSADO, Accion.REANUDAR): Estado.ACTIVO,
    (Estado.PAUSADO, Accion.ARCHIVAR): Estado.ARCHIVADO,
    (Estado.PAUSADO, Accion.REACTIVAR): Rechazo.NO_ESTA_ARCHIVADO,
    (Estado.ARCHIVADO, Accion.PAUSAR): Rechazo.VINCULO_ARCHIVADO,
    (Estado.ARCHIVADO, Accion.REANUDAR): Rechazo.VINCULO_ARCHIVADO,
    (Estado.ARCHIVADO, Accion.ARCHIVAR): Rechazo.YA_ESTA_ASI,
    (Estado.ARCHIVADO, Accion.REACTIVAR): Estado.ACTIVO,
}


def transicionar(estado: Estado, accion: Accion) -> Estado | Rechazo:
    """The state the link ends in, or why it does not move.

    There is no default. A `KeyError` here means somebody added a member to one
    of the enums and did not fill in the table, and that is worth crashing over:
    the alternative is a fallback that quietly allows or quietly forbids a case
    nobody decided.
    """
    return _TABLA[(estado, accion)]
