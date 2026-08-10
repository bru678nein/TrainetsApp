"""`/health/ready` and what it is actually able to notice.

Nothing covered this route before, which is uncomfortable given what it is for:
it exists so that a deployment cannot look healthy while being broken, and it was
the thing asserting the deployment was fine.

It could not notice the case that happened. The platform's database stayed on
`0005` while the image kept deploying up to `0007`, and this route answered `ok`
with a revision number that had to be read by a human who already knew which one
to expect. Every data endpoint was returning 500 against a column that did not
exist yet.
"""

from __future__ import annotations

import pytest

from app import main


@pytest.fixture(autouse=True)
def _sin_cache() -> None:
    """La cabeza se cachea con `lru_cache`, y cada test la mueve."""
    main._revision_que_este_codigo_necesita.cache_clear()


@pytest.fixture
def base_de_prueba(db, monkeypatch):
    """Apunta la readiness a la base de test.

    El conftest falsifica `deps.open_session`, y esta ruta abre la suya desde
    `app.db` — a propósito: comprobar que la base contesta no puede depender de
    la sesión con contexto de tenant que provee el router de datos. Son dos
    costuras distintas y hay que falsificar la que corresponde.
    """
    from contextlib import contextmanager

    import app.db as base

    @contextmanager
    def _sesion():
        yield db

    monkeypatch.setattr(base, "open_session", _sesion)


class TestConLaBaseAlDia:
    def test_responde_ok_con_la_revision(self, client, base_de_prueba) -> None:
        r = client.get("/health/ready")
        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["status"] == "ok"
        assert cuerpo["migracion"] == main._revision_que_este_codigo_necesita()

    def test_la_cabeza_sale_de_las_migraciones_y_no_de_una_constante(self) -> None:
        """Que la lea del directorio es lo que impide que se desactualice.

        Una constante en el código es un segundo lugar que actualizar, y el
        escenario que esta ruta tiene que cazar es exactamente el de alguien que
        actualizó uno solo.
        """
        from pathlib import Path

        cabeza = main._revision_que_este_codigo_necesita()
        migraciones = Path(main.__file__).resolve().parent.parent / "migrations" / "versions"
        archivos = [p.name for p in migraciones.glob("*.py")]
        assert any(n.startswith(cabeza) for n in archivos), (
            f"la cabeza {cabeza} no corresponde a ningún archivo de {archivos}"
        )


class TestConLaBaseAtrasada:
    def test_una_base_sin_migrar_da_503_y_no_ok(self, client, base_de_prueba, monkeypatch) -> None:
        """El caso que pasó en producción y que esta ruta no veía."""
        monkeypatch.setattr(main, "_revision_que_este_codigo_necesita", lambda: "9999")

        r = client.get("/health/ready")
        assert r.status_code == 503
        assert r.json()["status"] == "sin migrar"

    def test_dice_las_dos_revisiones_y_no_solo_que_algo_esta_mal(
        self, client, base_de_prueba, monkeypatch
    ) -> None:
        """Sin los dos números no se sabe en qué dirección está la diferencia.

        Falta migrar, o se deployó una imagen vieja contra una base ya migrada.
        Son dos problemas distintos con dos arreglos opuestos.
        """
        monkeypatch.setattr(main, "_revision_que_este_codigo_necesita", lambda: "9999")

        cuerpo = client.get("/health/ready").json()
        assert cuerpo["esperada"] == "9999"
        assert cuerpo["migracion"] != "9999"


class TestLivenessNoTocaLaBase:
    def test_health_responde_sin_consultar_nada(self, client, monkeypatch) -> None:
        """La distinción entre las dos rutas, verificada y no declarada.

        Si `/health` tocara la base, un corte de Postgres haría que el
        orquestador reiniciara un proceso que no tiene nada malo.
        """

        def explotar() -> None:
            raise AssertionError("/health no puede abrir una sesión")

        monkeypatch.setattr("app.db.open_session", explotar)
        assert client.get("/health").status_code == 200
