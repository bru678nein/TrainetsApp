# ADR 0004 — PyJWT en vez de python-jose, y caché de JWKS propio

Fecha: 2026-08-08 · Estado: aceptado

## Contexto

El ADR 0003 decidió verificar el token contra el JWKS del proveedor sin SDK,
pero no nombró con qué librería. `requirements.txt` traía
`python-jose[cryptography]>=3.3` desde antes de esa decisión, declarada y sin
usar por nadie.

El adaptador que trae el JWKS y lo cachea obliga a resolver dos cosas: con qué librería se verifica la firma, y si el caché de
claves lo escribimos nosotros o lo trae la librería.

Verificado en agosto de 2026, que es lo que `PLAN.md` §5 pide hacer en vez de
fiarse de una tabla escrita meses antes:

- **`python-jose` está prácticamente abandonado.** Sin releases en doce meses,
  cuatro CVEs conocidos —entre ellos CVE-2024-33664, una denegación de servicio
  por token JWE con alta compresión, corregida en 3.4.0— y la propia discusión
  abierta en el repositorio de FastAPI lo trata como tal. Snyk lo clasifica como
  posiblemente discontinuado.
- **PyJWT tiene mantenimiento sano**, con releases en los últimos meses. La
  documentación de verificación manual de Clerk lo usa en sus ejemplos.
- **El `PyJWKClient` de PyJWT tiene una falla conocida y sólo a medias
  corregida.** El advisory GHSA-fhv5-28vv-h8m8 (CVSS 3.7, disponibilidad)
  describe que `get_signing_key()` dispara una petición HTTP al JWKS por **cada**
  token con un `kid` desconocido, sin límite. Como el `kid` viaja en el header
  *sin verificar*, cualquiera sin autenticarse fabrica tráfico saliente
  ilimitado contra el proveedor.

El advisory recomienda dos mitigaciones: preservar el caché ante un fetch
fallido, y un cooldown de refresco. **PyJWT 2.13.0 implementó la primera y no la
segunda.** Antes de ese release, un error transitorio de red borraba el caché y
convertía un fallo puntual del proveedor en una caída de auth en toda la app.

## Decisión

**PyJWT reemplaza a `python-jose`.** Se saca `python-jose` de
`requirements.txt` ahora, porque está declarado sin usarse y arrastra CVEs sin
darnos nada. PyJWT entra cuando haya código que verifique firmas, y no antes:
declarar una dependencia antes de usarla es cómo llegamos a esta situación.

**El caché de JWKS es nuestro**, en `app/core/jwks.py`, y no `PyJWKClient`. La
firma sí va por librería: eso es criptografía y no se escribe a mano.

El motivo de no usar su cliente es que el cooldown habría que ponerlo igual, y
envolverlo significa parchear por encima de un caché de dos niveles —conjunto
completo con TTL de 300 s, más un LRU de claves individuales sin expiración—
cuya semántica no controlamos. El caché que la sección 2 del plan describe son
unas cuarenta líneas, hace exactamente lo que queremos y se testea con un
proveedor falso y un reloj falso, sin socket.

Queda documentado que esto es una excepción consciente a la preferencia por
librerías antes que código propio: la alternativa existe y se descarta con
motivo, no por gusto de escribir código.

## Consecuencias

**A favor.** El cooldown es nuestro y está testeado: mil `kid` inventados
producen dos peticiones al proveedor, no mil. El caché sobrevive a un proveedor
caído y sigue sirviendo lo que tenía, en vez de dejar sin auth a toda la app.
Ambas mitades del advisory quedan cubiertas, una de las cuales la librería no
cubre. Y el caché no depende de red para testearse, así que la lógica riesgosa
—que es la política, no el HTTP— se verifica en milisegundos.

**En contra.** Es código nuestro que hay que mantener: si el formato del JWKS
cambia o aparece un caso que no previmos, lo arreglamos nosotros y no llega por
un `pip install --upgrade`. Y hay que seguir el advisory: si PyJWT agrega el
cooldown más adelante, conviene revisar si vale reemplazar lo nuestro.

**Lo que no se resolvió.** `requirements.txt` usa rangos abiertos (`>=`), así
que CI puede instalar una versión más nueva que la del venv local y ponerse en
rojo sin que nadie haya tocado código. Es un problema de política de
dependencias más amplio que este ADR y queda anotado, no decidido.

## Referencias

- [GHSA-fhv5-28vv-h8m8 — PyJWKClient unbounded JWKS requests](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-fhv5-28vv-h8m8)
- [Changelog de PyJWT](https://pyjwt.readthedocs.io/en/latest/changelog.html)
- [`python-jose` en Snyk](https://security.snyk.io/package/pip/python-jose)
- [Por qué FastAPI todavía recomienda `python-jose`](https://github.com/fastapi/fastapi/discussions/9587)
- [PyJWKClient con caché destruida ante un fallo](https://github.com/jpadilla/pyjwt/issues/1162)
