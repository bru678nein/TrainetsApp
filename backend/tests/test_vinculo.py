"""State transitions of the coach-athlete link. Task T-022.

Written before the implementation, as article IV requires for the domain.

The whole point of this module is that pausing and archiving are not the same
thing, and the transition table is where that distinction is enforced rather
than assumed. The 003 spec separated them because collapsing them takes a
capability away from the coach: a paused athlete is still editable, so the coach
can prepare the programme for their return, and an archived one is not.

Every one of the twelve (state, action) pairs is here, including the eight that
must be rejected. A table with holes in it is a table that grows an `else` that
silently allows something.
"""

from __future__ import annotations

import pytest

from app.domain.vinculo import Accion, Estado, Rechazo, transicionar

# --- Lo que se puede hacer ----------------------------------------------------


@pytest.mark.parametrize(
    ("desde", "accion", "hasta"),
    [
        (Estado.ACTIVO, Accion.PAUSAR, Estado.PAUSADO),
        (Estado.PAUSADO, Accion.REANUDAR, Estado.ACTIVO),
        (Estado.ACTIVO, Accion.ARCHIVAR, Estado.ARCHIVADO),
        (Estado.PAUSADO, Accion.ARCHIVAR, Estado.ARCHIVADO),
        (Estado.ARCHIVADO, Accion.REACTIVAR, Estado.ACTIVO),
    ],
)
def test_las_transiciones_validas_devuelven_el_estado_siguiente(desde, accion, hasta):
    assert transicionar(desde, accion) is hasta


def test_se_puede_archivar_desde_los_dos_estados_vivos():
    """Archivar no exige pasar por pausado primero.

    Un entrenador que cierra una relación no tiene por qué hacer dos clics, y
    obligarlo inventaría un estado intermedio que nadie pidió.
    """
    assert transicionar(Estado.ACTIVO, Accion.ARCHIVAR) is Estado.ARCHIVADO
    assert transicionar(Estado.PAUSADO, Accion.ARCHIVAR) is Estado.ARCHIVADO


# --- Lo que no ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("desde", "accion"),
    [
        (Estado.PAUSADO, Accion.PAUSAR),
        (Estado.ACTIVO, Accion.REANUDAR),
        (Estado.ARCHIVADO, Accion.ARCHIVAR),
    ],
)
def test_repetir_lo_que_ya_pasó_se_rechaza_por_redundante(desde, accion):
    assert transicionar(desde, accion) is Rechazo.YA_ESTA_ASI


@pytest.mark.parametrize("accion", [Accion.PAUSAR, Accion.REANUDAR])
def test_sobre_un_vinculo_archivado_no_se_pausa_ni_se_reanuda(accion):
    """Y el motivo es propio, no `YA_ESTA_ASI`.

    Es la diferencia entre "eso ya está hecho" y "el vínculo terminó, reactivalo
    primero". La segunda le dice a quien está del otro lado qué hacer; la primera
    lo manda a adivinar.
    """
    assert transicionar(Estado.ARCHIVADO, accion) is Rechazo.VINCULO_ARCHIVADO


@pytest.mark.parametrize("desde", [Estado.ACTIVO, Estado.PAUSADO])
def test_no_se_reactiva_lo_que_no_estaba_archivado(desde):
    assert transicionar(desde, Accion.REACTIVAR) is Rechazo.NO_ESTA_ARCHIVADO


# --- Que la tabla no tenga agujeros -------------------------------------------


def test_las_doce_combinaciones_estan_decididas():
    """Ningún par (estado, acción) puede quedar sin respuesta.

    Este test es el que hace que agregar un estado —el atleta que se va por su
    cuenta, hoy fuera de alcance— sea imposible de hacer a medias: aparecen
    cuatro combinaciones nuevas y hay que decidir las cuatro.
    """
    for estado in Estado:
        for accion in Accion:
            resultado = transicionar(estado, accion)
            assert isinstance(resultado, Estado | Rechazo), (
                f"({estado.value}, {accion.value}) no está decidido"
            )


def test_pausado_no_es_archivado():
    """El guardián de la distinción que la spec tomó como decisión.

    Si alguien colapsa los dos estados, esto cae antes que cualquier test de
    base de datos, y lo dice con el nombre puesto.
    """
    assert Estado.PAUSADO is not Estado.ARCHIVADO
    assert transicionar(Estado.PAUSADO, Accion.REANUDAR) is Estado.ACTIVO
    assert transicionar(Estado.ARCHIVADO, Accion.REANUDAR) is Rechazo.VINCULO_ARCHIVADO
