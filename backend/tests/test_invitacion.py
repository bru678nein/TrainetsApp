"""Invitation tokens: generation, hashing, expiry.

Written before the implementation, as domain code requires here.

No clock and no database. `emitir` takes the moment of issue as an argument for
the same reason `identify` does: a function that reads the clock has
expiry tests that pass at 11:59 and fail at 12:00, and those tests get deleted
rather than fixed.

The test that matters most here is the last one. The link travels over WhatsApp
and ends up in a chat history, so the one thing this module must guarantee is
that the clear token never reaches storage — and that is checked by looking at
what would be stored, not by reading the code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.invitacion import VIGENCIA, emitir, esta_vencida, hash_de

EMISION = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


# --- Generación ---------------------------------------------------------------


def test_dos_invitaciones_seguidas_no_comparten_token():
    primero, _ = emitir(EMISION)
    segundo, _ = emitir(EMISION)
    assert primero != segundo


def test_el_token_tiene_entropia_suficiente_para_no_adivinarse():
    """32 bytes de `secrets`, que en base64 urlsafe son 43 caracteres.

    El umbral no es estético: este token es la única credencial que protege los
    datos personales de un atleta, y viaja por un canal que no controlamos.
    """
    token, _ = emitir(EMISION)
    assert len(token) >= 43


def test_el_hash_es_estable():
    assert hash_de("un-token") == hash_de("un-token")
    assert hash_de("un-token") != hash_de("otro-token")


# --- Vencimiento --------------------------------------------------------------


def test_la_vigencia_es_de_siete_dias():
    """Está acá para que cambiarlo sea una decisión visible."""
    assert timedelta(days=7) == VIGENCIA


def test_el_vencimiento_se_calcula_desde_la_emision():
    _, guardable = emitir(EMISION)
    assert guardable.expires_at == EMISION + VIGENCIA


def test_a_los_seis_dias_sirve_y_a_los_ocho_no():
    """El vencimiento, en el dominio."""
    _, guardable = emitir(EMISION)
    assert not esta_vencida(guardable.expires_at, EMISION + timedelta(days=6))
    assert esta_vencida(guardable.expires_at, EMISION + timedelta(days=8))


def test_el_instante_exacto_del_vencimiento_ya_no_sirve():
    """Un borde que se decide una vez o se decide distinto en cada llamada."""
    _, guardable = emitir(EMISION)
    assert esta_vencida(guardable.expires_at, guardable.expires_at)


# --- Lo que no se guarda ------------------------------------------------------


def test_el_token_en_claro_no_aparece_en_lo_que_se_persiste():
    """Se busca el token adentro de lo que se va a guardar, no en el código.

    Leer la implementación y concluir que está bien es exactamente el chequeo
    que deja de hacerse cuando alguien agrega un campo. Esto no.
    """
    token, guardable = emitir(EMISION)
    serializado = repr(guardable)
    assert token not in serializado
    for valor in vars(guardable).values():
        assert token != valor
        assert token.encode() != valor


def test_lo_que_se_guarda_es_el_hash_del_token_emitido():
    """Y el hash tiene que ser el del token que efectivamente se entregó.

    Sin esto, `emitir` podría devolver un token y guardar el hash de otro: todos
    los tests de arriba seguirían pasando y ninguna invitación funcionaría.
    """
    token, guardable = emitir(EMISION)
    assert guardable.token_hash == hash_de(token)
