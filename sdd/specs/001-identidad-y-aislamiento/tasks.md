# Tareas — 001 Identidad y aislamiento por tenant

Del `plan.md` de esta carpeta. Cada tarea declara **cómo se sabe que está
hecha**: si no se puede verificar, está mal escrita.

Los commits referencian su tarea con `T-NNN` en el cuerpo (artículo X). Sin eso,
la trazabilidad commit → tarea → plan → spec se corta en el primer eslabón, que
es lo que pasa hoy.

Estado: `pendiente` · `en curso` · `hecha`

---

## Hechas

| ID | Tarea | Verificado con |
|---|---|---|
| T-006a | `tenant_session` como única puerta a la base; `get_db` deja de ser dependencia pública | 71 tests |
| T-016a | Test de composición: toda ruta `/api` depende de `tenant_session` | falla si se le saca la dependencia a un endpoint |
| T-001 | Migración de identidad: `app_user`, `user_id` en `coach` y `athlete`, índice parcial | `upgrade`/`downgrade` ida y vuelta sobre la base sembrada |
| T-002 | Modelos al día | `test_la_migracion_no_divergio_de_los_modelos` |
| T-003 | `docs/schema.sql` al día | tablas y columnas comparadas contra `models.py` |
| T-014a | La fixture deja de saltear la cadena de seguridad | con una subdependencia que falla siempre, la suite falla — antes pasaba entera |
| T-004 | Dominio: claims a identidad o motivo de rechazo | 16 tests escritos antes; sacando el chequeo de `azp` fallan 3, invirtiendo el orden de los chequeos fallan 3 |
| T-005 | Adaptador JWKS con caché por `kid` y cooldown de refresco | 12 tests con proveedor y reloj falsos; sacando el cooldown, mil `kid` inventados pasan de 2 peticiones a 1001 |
| T-006 | `require_tenant_context` y `tenant_session`: token → identidad → rol → `set_config` → sesión | 34 tests con claves RSA reales; sacando el chequeo de rol caen 2, poniendo un default caen 2, interpolando el `sub` en vez de bindearlo cae la de inyección |

Las de letra se hicieron antes que el resto a propósito, para que el commit que
agregue la seguridad no venga mezclado con un refactor de seis firmas ni con un
arreglo del arnés de tests. Lo que falta de ellas es el contenido, en T-006,
T-014 y T-016.

T-014a no estaba prevista: apareció al revisar si los tests de T-015 a T-017 iban
a verificar algo de verdad. No iban. Con `dependency_overrides` sobre
`tenant_session`, toda la cadena que agrega T-006 quedaba salteada y la suite
seguía verde.

T-003 salió más grande de lo previsto: la sección de RLS de `schema.sql` asumía
`coach_id` en todas las tablas, `ENABLE` sin `FORCE`, y `current_setting` con
`missing_ok`. Las tres corregidas.

## Base de datos

**T-001 — Migración de identidad.** Crear `app_user`; agregar `user_id` a
`coach` y `athlete`; poblar desde `auth_user_id`; índice parcial
`(coach_id, user_id) WHERE user_id IS NOT NULL`; borrar las columnas viejas.

*Hecha cuando:* `alembic upgrade head` seguido de `downgrade base` corre limpio
sobre una base con la planilla importada, y el coach y el atleta existentes
conservan su identidad. El `downgrade` falla ruidosamente si una persona tiene
más de un vínculo, porque eso no entra en el modelo viejo.
*Bloquea a:* todas las de RLS.

**T-002 — Modelos al día.** `models.py` refleja T-001; `MANUALLY_MANAGED`
incluye el índice parcial.

*Hecha cuando:* `test_la_migracion_no_divergio_de_los_modelos` pasa.

**T-003 — `docs/schema.sql` al día.** Refleja el modelo nuevo y las policies
reales, no las que asumen `coach_id` en todas las tablas.

*Hecha cuando:* las tablas de `schema.sql` coinciden con `models.py` y los
caminos al tenant coinciden con la sección 4 del plan.

**T-007 — Rol de base sin privilegios.** La app se conecta con un rol que no es
dueño de las tablas. `.env.example` y el DSN de CI actualizados.

*Hecha cuando:* conectando con ese rol, un `SELECT` sin contexto de tenant
devuelve error, no filas. Es lo que hace que `FORCE ROW LEVEL SECURITY` importe.

**T-008 — Migración de RLS.** La función `app_current_user_id()`, `ENABLE` +
`FORCE`, y **dos** policies por tabla —`<tabla>_as_coach` y `<tabla>_as_athlete`—
con los caminos de la sección 4 del plan. `app_user` lleva la suya, escrita
directo contra `auth_user_id` para no recursionar.

*Hecha cuando:* con contexto del coach A, una consulta directa a `logged_set`
—la tabla más profunda— no devuelve nada de B; **y** con contexto de atleta, la
misma consulta devuelve sólo lo propio. Las dos mitades: una policy de coach
correcta con la de atleta ausente pasa el primer test y deja el rol atleta viendo
todo.

**T-008b — `WITH CHECK` en `logged_set`.** El `INSERT` exige que la serie
registrada le haya sido prescrita al mismo atleta que la firma.

*Hecha cuando:* un atleta que manda su propio `athlete_id` con un
`prescribed_set_id` de otro es rechazado por la base, no por un `if`. Es el
criterio de aceptación 4, y **no lo cubre `USING`**: `USING` no se aplica a un
`INSERT`. Va aparte de T-008 para que no se dé por hecha con los tests de lectura
en verde.

**T-009 — Policy de `exercise`.** El catálogo global (`coach_id IS NULL`) sigue
visible para todos, en los dos roles.

*Hecha cuando:* A ve sus ejercicios y los globales, y ninguno de B; y el atleta
ve los globales más los de su entrenador, que son los que aparecen en su sesión.

## Autenticación

**T-004 — Dominio: claims a identidad.** Función pura que recibe claims
decodificados y configuración esperada, y devuelve identidad o motivo de
rechazo. **Test antes que implementación** (artículo IV).

*Hecha cuando:* hay test para vencido, `nbf` futuro, `azp` de otro origen, `iss`
incorrecto y algoritmo inesperado; y no importa `httpx` ni `fastapi`.

**T-005 — Adaptador JWKS.** Trae el JWKS, cachea por `kid`, refresca ante `kid`
desconocido — **con cooldown**.

El enunciado original terminaba en "refresca ante `kid` desconocido", y así tal
cual es una vulnerabilidad: el `kid` viaja en el header *sin verificar*, así que
refrescar ante cada uno desconocido le da a cualquiera, sin autenticarse, una
forma de generar tráfico saliente ilimitado contra el proveedor. Es el advisory
GHSA-fhv5-28vv-h8m8 contra el cliente de la propia PyJWT. Ver el ADR 0004.

*Hecha cuando:* una rotación de claves simulada se resuelve sin reiniciar; mil
`kid` inventados producen dos peticiones al proveedor y no mil; y un proveedor
caído sigue sirviendo lo cacheado en vez de dejar sin auth a toda la app.

**T-006 — `require_tenant_context` y `tenant_session`.** Token → identidad →
header `Active-Role` → `SET LOCAL` → cede la sesión. Sin default.

El `SET LOCAL` es de las **dos** variables del contrato de la sección 4:
`app.current_auth_user_id` (el `sub`, texto, sin castear) y `app.active_role`.
Ninguna se deriva leyendo la base: si hiciera falta una consulta para armar el
contexto, esa consulta correría sin contexto.

*Hecha cuando:* los cuatro casos de la tabla de la sección 3 del plan tienen
test: header ausente `400`, valor inválido `400`, rol no poseído `403`, rol
válido resuelve.

Detalle que apareció al implementarla y que el plan no decía: **`SET LOCAL` no
acepta parámetros.** Usarlo obligaría a pegar el `sub` dentro de la sentencia, y
el `sub` viene de afuera. Se usa `set_config(nombre, valor, true)`, que es lo
mismo —el tercer argumento es `is_local`— pero con el valor bindeado. Tiene test
propio: un `sub` con comillas termina en `403` y no en SQL ejecutado.

**T-013 — Cierre de sesión.** El token anterior deja de servir.

*Hecha cuando:* criterio 8 de la spec, automatizado.

## Endpoints

**T-010 — Montar el router con la dependencia.** `dependencies=[Depends(
require_tenant_context)]` y los endpoints actuales usando la sesión que provee.

*Hecha cuando:* la suite existente sigue pasando entera y T-016a sigue verde.
Sin número: cuando esta tarea se escribió eran 68 y hoy son más, y un criterio
que envejece deja de poder cumplirse tal como está escrito.

**T-011 — Alta de entrenador en el primer login.**

*Hecha cuando:* una identidad sin perfil de entrenador lo obtiene al entrar, y
ve su espacio vacío.

**T-012 — Crear atleta sin cuenta.** Dentro del espacio del entrenador.

*Hecha cuando:* la ficha existe con `user_id` nulo y se le puede prescribir.

## Verificación

**T-014 — Fixtures.** Dos entrenadores con un atleta cada uno, y una persona con
perfil de entrenador más ficha de atleta en su propio espacio.

Además: un cliente para los tests de seguridad con transacción real por request.
La fixture `db` actual comparte una transacción externa entre requests, y ahí el
`SET LOCAL` del primero sigue visible para el segundo — medido, no supuesto. El
test que verifica que una sesión sin contexto tira error no lo puede observar si
la transacción ya trae contexto de antes.

*Hecha cuando:* las usan T-015 a T-017 sin duplicar armado, y dos requests
seguidos con identidades distintas no comparten contexto de tenant.

**T-014a — La fixture no saltea la cadena de seguridad.** `conftest.py` deja de
usar `dependency_overrides` sobre `tenant_session` y falsifica `open_session`.

*Hecha cuando:* colgándole a `tenant_session` una subdependencia que falla
siempre, la suite falla. Con el override anterior pasaban los 71 tests, T-016a
incluido. Adelantada por el mismo motivo que T-006a y T-016a: que el commit que
agregue la seguridad no venga mezclado con un arreglo del arnés.

**T-015 — Recorrido de rutas: sin credenciales.** Toda ruta fuera de la lista
blanca responde `401`.

*Hecha cuando:* pasa, y agregar una ruta nueva sin declararla lo rompe.

**T-016 — Recorrido de rutas: recurso ajeno y sin header.** Criterios 2, 3 y el
`400` por header ausente.

*Hecha cuando:* pasa para todas las rutas, y sacarle la dependencia a un
endpoint lo rompe. **Esta es la tarea que cumple el artículo III**, hoy marcado
como incumplido en la tabla de cumplimiento de la constitución.

**T-017 — Criterios 9 a 11.** Coach que se entrena a sí mismo; persona vinculada
a dos entrenadores; coach que es atleta de otro sin ver su espacio.

*Hecha cuando:* los tres criterios tienen test.

## Cierre

**T-018 — Documentación.** `README.md`, backlog de `sdd/README.md`, y la tabla de
cumplimiento de la constitución: los artículos III y X dejan de estar en deuda.

*Hecha cuando:* ninguna afirmación de la tabla de cumplimiento es falsa. Es la
última porque hasta que T-016 no pase, el artículo III sigue sin cumplirse.

---

## Orden

T-001 abre todo. Después, dos caminos que no se pisan: base (T-002, T-003,
T-007, T-008, T-008b, T-009) y auth (T-004, T-005, T-006). Los dos tienen que
estar antes de T-010, y T-014 antes de las de verificación.

Dieciocho más las cuatro con letra. Las letras son mitades de una tarea que se
parten para que el diff se lea, no tareas nuevas: el límite de veinte de
`sdd/README.md` se cuenta sobre las numeradas. Si aparece una T-019, ahí sí algo
de acá era otra feature.
