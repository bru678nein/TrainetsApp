"""Coach B asking for coach A's data.

Someone else's identifier answers exactly
like one that does not exist. Not a different message, not a different status —
the response must not distinguish "not yours" from "not there", because a
distinguishable answer is an existence oracle.

This holds for *every* route that returns data, which is what
the full route walk enforces. This file goes first with the
routes spelled out, to find out whether RLS delivers it for free or whether the
endpoints need work. Assuming it does would be the third assumption of this kind
to turn out wrong.
"""

from __future__ import annotations

import re
import uuid

import pytest

from tests.conftest import SIN_ROL, rutas_de_datos

INEXISTENTE = "00000000-0000-0000-0000-000000000000"

# What each path parameter has to be filled with, and the body a write needs.
# Declared rather than guessed: a route with a parameter nobody listed here
# fails `test_toda_ruta_declara_como_ejercitarla`, so adding an endpoint forces
# a decision instead of quietly going uncovered.
PARAMETROS = {"athlete_id", "session_id", "set_id"}

CUERPOS: dict[str, dict[str, object]] = {
    "/api/sets/{set_id}/log": {"reps": 5, "load_kg": 50, "rir": 2},
}

# Routes that take no resource identifier, so "someone else's id" does not apply
# to them. They still have to leak nothing, which is what
# `test_el_listado_de_b_no_trae_atletas_de_a` checks — one test per entry, and
# the entry is what says somebody looked.
SIN_IDENTIFICADOR = {"/api/athletes"} | SIN_ROL


def _parametros(ruta: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", ruta))


def _metodo(route) -> str:
    """The verb to exercise. GET when it has one, otherwise whatever it is."""
    metodos = route.methods - {"HEAD", "OPTIONS"}
    return "GET" if "GET" in metodos else next(iter(sorted(metodos)))


def _id_de_ruta(route) -> str:
    return f"{_metodo(route)} {route.path}"


@pytest.fixture
def coach_b(db) -> str:
    """A second coach, with nothing of their own. Returns their `sub`."""
    from app.models import AppUser, Coach

    marca = uuid.uuid4().hex[:8]
    sub = f"coach-b-{marca}"
    persona = AppUser(auth_user_id=sub, email=f"b-{marca}@example.com", display_name="Coach B")
    db.add(persona)
    db.flush()
    db.add(Coach(user_id=persona.id))
    db.flush()
    return sub


@pytest.fixture
def como_b(raw_client, mint, coach_b):
    """Requests signed as coach B."""

    def _pedir(metodo: str, ruta: str, **kwargs):
        return raw_client.request(
            metodo,
            ruta,
            headers={"Authorization": f"Bearer {mint(sub=coach_b)}", "Active-Role": "coach"},
            **kwargs,
        )

    return _pedir


@pytest.fixture
def recursos_de_a(client, seeded) -> dict[str, str]:
    """Real identifiers belonging to coach A, taken from the seeded spreadsheet."""
    atletas = client.get("/api/athletes").json()
    assert atletas, "la planilla no dejó atletas: el test no probaría nada"
    atleta = atletas[0]["id"]
    agenda = client.get(f"/api/athletes/{atleta}/sessions").json()
    assert agenda, "el atleta de A no tiene sesiones"
    detalle = client.get(f"/api/sessions/{agenda[0]['id']}").json()
    return {
        "athlete_id": atleta,
        "session_id": agenda[0]["id"],
        "set_id": detalle["blocks"][0]["sets"][0]["id"],
    }


def test_el_listado_de_b_no_trae_atletas_de_a(como_b):
    """The cheapest thing to get wrong.

    The message reports how many leaked and their ids, never the rows. A failure
    message is printed by CI, and `full_name` holds the name of a real person
    from a spreadsheet that is unversioned precisely so that it stays out of the
    repository. A test that leaks it on failure defeats that on the worst day.
    """
    r = como_b("GET", "/api/athletes")
    assert r.status_code == 200
    filtrados = [a["id"] for a in r.json()]
    assert filtrados == [], f"B ve {len(filtrados)} atletas ajenos: {filtrados}"


def test_toda_ruta_declara_como_ejercitarla():
    """This holds for *every* route, not the ones somebody listed.

    The walk below can only exercise a route whose parameters it knows how to
    fill. Rather than skipping the ones it does not, this fails — so adding an
    endpoint with a new kind of identifier breaks the suite until someone
    declares it, which is the only version of "every endpoint" that stays true
    as the API grows.
    """
    sin_declarar = {
        r.path: _parametros(r.path) - PARAMETROS
        for r in rutas_de_datos()
        if _parametros(r.path) - PARAMETROS
    }
    assert not sin_declarar, (
        f"rutas con parámetros que el recorrido no sabe llenar: {sin_declarar}. "
        f"Agregalos a PARAMETROS y a la fixture `recursos_de_a`."
    )

    huerfanas = [
        r.path
        for r in rutas_de_datos()
        if not _parametros(r.path) and r.path not in SIN_IDENTIFICADOR
    ]
    assert not huerfanas, (
        f"rutas sin identificador y sin test propio: {huerfanas}. Declaralas en "
        f"SIN_IDENTIFICADOR y escribí el test que verifique que no filtran."
    )


@pytest.mark.parametrize(
    "route",
    [r for r in rutas_de_datos() if _parametros(r.path)],
    ids=_id_de_ruta,
)
def test_un_recurso_ajeno_responde_igual_que_uno_inexistente(como_b, recursos_de_a, route):
    """On every route the app exposes.

    Both halves are compared: status *and* body. A 404 whose message says
    "not yours" would pass a status-only check and still be an oracle.

    Parametrised over the routes discovered in the app rather than a written
    list, so an endpoint added tomorrow is covered the day it is added.
    """
    metodo, plantilla = _metodo(route), route.path
    cuerpo = CUERPOS.get(plantilla)
    kwargs = {"json": cuerpo} if cuerpo is not None else {}

    ajeno = como_b(metodo, plantilla.format(**recursos_de_a), **kwargs)
    fantasma = como_b(
        metodo,
        plantilla.format(**dict.fromkeys(PARAMETROS, INEXISTENTE)),
        **kwargs,
    )

    assert ajeno.status_code == fantasma.status_code, (
        f"{metodo} {plantilla}: ajeno da {ajeno.status_code} y inexistente "
        f"{fantasma.status_code} — la diferencia delata que el recurso existe"
    )
    # Compared, never printed. When they differ the interesting one is the
    # foreign response, and that is exactly the one that may carry another
    # person's data — into a CI log, on the day it breaks.
    assert ajeno.json() == fantasma.json(), (
        f"{metodo} {plantilla}: mismo status pero cuerpos distintos, así que la "
        f"respuesta igual delata que el recurso existe. Los cuerpos no se "
        f"imprimen: el ajeno puede traer datos de otra persona."
    )


@pytest.mark.parametrize(
    "route", [r for r in rutas_de_datos() if r.path not in SIN_ROL], ids=_id_de_ruta
)
def test_toda_ruta_exige_el_header_de_rol(raw_client, mint, recursos_de_a, route):
    """The third leg, and the one that catches a missing dependency.

    With valid credentials and no `Active-Role`, every data route answers 400.
    An endpoint that somehow bypassed `require_tenant_context` would answer 200
    here, and this is what notices — including on a route that touches no
    database, where nothing else would.
    """
    metodo, plantilla = _metodo(route), route.path
    cuerpo = CUERPOS.get(plantilla)
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    r = raw_client.request(
        metodo,
        plantilla.format(**recursos_de_a),
        headers={"Authorization": f"Bearer {mint()}"},
        **kwargs,
    )
    assert r.status_code == 400, f"{metodo} {plantilla} respondió {r.status_code} sin Active-Role"


@pytest.mark.parametrize("route", rutas_de_datos(), ids=_id_de_ruta)
def test_toda_ruta_rechaza_a_quien_no_se_identifica(raw_client, recursos_de_a, route):
    """No credentials, no data. On every route, discovered not listed.

    The allowlist that decides which routes are exempt lives in conftest as
    SIN_TENANT, and it is explicit so that adding a route breaks this until
    somebody consciously puts it on one side or the other.
    """
    metodo, plantilla = _metodo(route), route.path
    cuerpo = CUERPOS.get(plantilla)
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    r = raw_client.request(metodo, plantilla.format(**recursos_de_a), **kwargs)
    assert r.status_code == 401, f"{metodo} {plantilla} respondió {r.status_code} sin credenciales"
