"""CORS, y el header custom que se olvida.

Sin esto el navegador rechaza cada request antes de que salga, y el error que
muestra no menciona al servidor. Nada de eso aparece probando con `curl`, que no
hace preflight: es un bug que sólo existe adentro de un navegador.

`Active-Role` es el que importa. Es un header custom, así que dispara un
preflight `OPTIONS`, y si no está declarado el navegador falla hablando de CORS
sin nombrarlo. Se busca en la capa equivocada durante horas.
"""

from __future__ import annotations

import pytest

from app import main

ORIGEN_AJENO = "https://otra-cosa.example.com"


def _preflight(client, origen: str, header: str = "active-role"):
    return client.options(
        "/api/athletes",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": header,
        },
    )


@pytest.fixture
def origen(app_de_prueba) -> str:
    """El origen que la app acepta, leído de la configuración falsa de la suite.

    Depende de `app_de_prueba` para que la fixture `auth` ya haya parcheado
    `main.get_settings`. Sin esa dependencia esto leía el `.env` de la máquina, y
    los tests pasaban por un archivo que no está versionado.
    """
    from app import main

    return main.get_settings().auth_authorized_party


class TestElPreflightPasa:
    def test_el_navegador_puede_mandar_active_role(self, client, origen) -> None:
        r = _preflight(client, origen)
        assert r.status_code == 200
        permitidos = r.headers["access-control-allow-headers"].lower()
        assert "active-role" in permitidos

    def test_tambien_authorization(self, client, origen) -> None:
        r = _preflight(client, origen, header="authorization")
        assert "authorization" in r.headers["access-control-allow-headers"].lower()

    def test_la_respuesta_declara_el_origen(self, client, origen) -> None:
        r = _preflight(client, origen)
        assert r.headers["access-control-allow-origin"] == origen


class TestUnOrigenAjenoNoPasa:
    def test_no_se_le_responde_con_permiso(self, client, origen) -> None:
        """El control. Sin esto, `allow_origins=["*"]` pasaría todo lo de arriba."""
        r = _preflight(client, ORIGEN_AJENO)
        assert r.headers.get("access-control-allow-origin") != ORIGEN_AJENO


class TestElOrigenYElAzpSonElMismoValor:
    def test_no_hay_una_segunda_configuracion_que_pueda_divergir(self) -> None:
        """Son el mismo dato, no dos que hay que mantener iguales.

        Si alguien agrega un ajuste propio para CORS, este test empieza a mirar
        el lugar equivocado y hay que decidirlo a conciencia. Que sea un solo
        valor es lo que hace que no puedan desincronizarse — y desincronizados el
        síntoma es un 401 que parece problema de token, no de CORS.
        """
        from app.core.config import Settings

        campos = set(Settings.model_fields)
        assert "auth_authorized_party" in campos
        assert not [c for c in campos if "cors" in c or "origin" in c], (
            f"apareció una configuración de origen aparte: {campos}"
        )


class TestLaConfiguracionSeLeeTarde:
    def test_importar_la_app_no_exige_entorno(self) -> None:
        """El middleware se arma en el primer request, no al importar.

        `add_middleware` corre al importar el módulo, así que leer la
        configuración ahí obligaría a tener el entorno completo para inspeccionar
        rutas o correr los tests de dominio en un clon limpio.
        """
        assert main.CorsPerezoso(lambda *a: None)._cors is None
