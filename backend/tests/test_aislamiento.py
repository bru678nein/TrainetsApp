"""Coach B asking for coach A's data. The core of T-016.

Acceptance criterion 2 of the spec: someone else's identifier answers exactly
like one that does not exist. Not a different message, not a different status —
the response must not distinguish "not yours" from "not there", because a
distinguishable answer is an existence oracle.

Criterion 3 says this holds for *every* route that returns data, which is what
the route walk in T-016 proper will enforce. This file goes first with the
routes spelled out, to find out whether RLS delivers it for free or whether the
endpoints need work. Assuming it does would be the third assumption of this kind
to turn out wrong.
"""

from __future__ import annotations

import uuid

import pytest

INEXISTENTE = "00000000-0000-0000-0000-000000000000"


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
    """Criterion 1, and the cheapest thing to get wrong.

    The message reports how many leaked and their ids, never the rows. A failure
    message is printed by CI, and `full_name` holds the name of a real person
    from a spreadsheet that is unversioned precisely so that it stays out of the
    repository. A test that leaks it on failure defeats that on the worst day.
    """
    r = como_b("GET", "/api/athletes")
    assert r.status_code == 200
    filtrados = [a["id"] for a in r.json()]
    assert filtrados == [], f"B ve {len(filtrados)} atletas ajenos: {filtrados}"


@pytest.mark.parametrize(
    "metodo,plantilla,cuerpo",
    [
        ("GET", "/api/athletes/{athlete_id}/sessions", None),
        ("GET", "/api/athletes/{athlete_id}/volume", None),
        ("GET", "/api/athletes/{athlete_id}/adherence", None),
        ("GET", "/api/sessions/{session_id}", None),
        ("PUT", "/api/sets/{set_id}/log", {"reps": 5, "load_kg": 50, "rir": 2}),
    ],
)
def test_un_recurso_ajeno_responde_igual_que_uno_inexistente(
    como_b, recursos_de_a, metodo, plantilla, cuerpo
):
    """Criterion 2, route by route.

    Both halves are compared: status *and* body. A 404 whose message says
    "not yours" would pass a status-only check and still be an oracle.
    """
    kwargs = {"json": cuerpo} if cuerpo is not None else {}

    ajeno = como_b(metodo, plantilla.format(**recursos_de_a), **kwargs)
    fantasma = como_b(
        metodo,
        plantilla.format(athlete_id=INEXISTENTE, session_id=INEXISTENTE, set_id=INEXISTENTE),
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
