# Tareas — 001 Identidad y aislamiento por tenant

Del `plan.md` de esta carpeta. Cada tarea declara **cómo se sabe que está
hecha**: si no se puede verificar, está mal escrita.

Los commits referencian su tarea con `T-NNN` en el cuerpo (artículo X). Sin eso,
la trazabilidad commit → tarea → plan → spec se corta en el primer eslabón, que
es lo que pasa hoy.

Estado: `pendiente` · `en curso` · `hecha`

---

## Adelantadas

| ID | Tarea | Estado |
|---|---|---|
| T-006a | `tenant_session` como única puerta a la base; `get_db` deja de ser dependencia pública | hecha |
| T-016a | Test de composición: toda ruta `/api` depende de `tenant_session` | hecha |
| T-001 | Migración de identidad: `app_user`, `user_id` en `coach` y `athlete`, índice parcial | hecha |
| T-002 | Modelos al día | hecha |

Se hicieron antes que el resto a propósito, para que el commit que agregue la
seguridad no venga mezclado con un refactor de seis firmas. Lo que falta de
ellas es el contenido, en T-006 y T-016.

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

**T-008 — Migración de RLS.** `ENABLE` + `FORCE` y policies por tabla, con los
caminos de la sección 4 del plan.

*Hecha cuando:* con contexto del coach A, una consulta directa a `logged_set`
—la tabla más profunda— no devuelve nada de B.

**T-009 — Policy de `exercise`.** El catálogo global (`coach_id IS NULL`) sigue
visible para todos.

*Hecha cuando:* A ve sus ejercicios y los globales, y ninguno de B.

## Autenticación

**T-004 — Dominio: claims a identidad.** Función pura que recibe claims
decodificados y configuración esperada, y devuelve identidad o motivo de
rechazo. **Test antes que implementación** (artículo IV).

*Hecha cuando:* hay test para vencido, `nbf` futuro, `azp` de otro origen, `iss`
incorrecto y algoritmo inesperado; y no importa `httpx` ni `fastapi`.

**T-005 — Adaptador JWKS.** Trae el JWKS, cachea por `kid`, refresca ante `kid`
desconocido.

*Hecha cuando:* una rotación de claves simulada se resuelve sin reiniciar.

**T-006 — `require_tenant_context` y `tenant_session`.** Token → identidad →
header `Active-Role` → `SET LOCAL` → cede la sesión. Sin default.

*Hecha cuando:* los cuatro casos de la tabla de la sección 3 del plan tienen
test: header ausente `400`, valor inválido `400`, rol no poseído `403`, rol
válido resuelve.

**T-013 — Cierre de sesión.** El token anterior deja de servir.

*Hecha cuando:* criterio 8 de la spec, automatizado.

## Endpoints

**T-010 — Montar el router con la dependencia.** `dependencies=[Depends(
require_tenant_context)]` y los endpoints actuales usando la sesión que provee.

*Hecha cuando:* los 68 tests existentes pasan y T-016a sigue verde.

**T-011 — Alta de entrenador en el primer login.**

*Hecha cuando:* una identidad sin perfil de entrenador lo obtiene al entrar, y
ve su espacio vacío.

**T-012 — Crear atleta sin cuenta.** Dentro del espacio del entrenador.

*Hecha cuando:* la ficha existe con `user_id` nulo y se le puede prescribir.

## Verificación

**T-014 — Fixtures.** Dos entrenadores con un atleta cada uno, y una persona con
perfil de entrenador más ficha de atleta en su propio espacio.

*Hecha cuando:* las usan T-015 a T-017 sin duplicar armado.

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
T-007, T-008, T-009) y auth (T-004, T-005, T-006). Los dos tienen que estar
antes de T-010, y T-014 antes de las de verificación.

Dieciocho más las dos adelantadas. El límite de `sdd/README.md` son veinte; si
aparecen más, algo de acá era otra feature.
