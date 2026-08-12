# Tareas — 003 Invitaciones y ciclo de vida del vínculo

Del `plan.md` de esta carpeta. Cada tarea declara **cómo se sabe que está hecha**:
si no se puede verificar, está mal escrita.

Los commits referencian su tarea con `T-NNN` en el cuerpo (artículo X).

**La numeración sigue desde la 001 y no reinicia en T-001.** Dos features con un
`T-004` cada una cortan la trazabilidad commit → tarea → plan → spec justo en el
eslabón que el artículo X quiere garantizar, y el cuerpo de un commit no dice a
qué carpeta pertenece el número.

Estado: `pendiente` · `en curso` · `hecha`

---

## Hechas

| ID | Tarea | Verificado con |
|---|---|---|
| T-024 | Migración: tabla `invitation` | 5 tests; volviendo el índice parcial en total cae 1, sacándole la unicidad cae otro, y quitándosela al hash cae un tercero |
| T-025 | RLS de `invitation` | 4 tests como rol de aplicación; sacando el gate por rol activo cae el de la persona con los dos roles, y sacando el chequeo de dueño caen 2 |
| T-026 | Helpers `app_vinculo_escribible_<tabla>` | 21 tests, las seis tablas parametrizadas; 6 mutaciones cazadas y verificadas como fallas de test y no de montaje —invertir la respuesta, confundir pausado con archivado, olvidar una tabla, no revocar `EXECUTE`, no fijar `search_path`, sacar `SECURITY DEFINER` |
| T-027 | Las 18 policies `RESTRICTIVE` | 39 tests, seis tablas × cuatro afirmaciones; sacando cada una de las 18 por separado cae un test. Destapó un defecto anterior: las policies permisivas de la 0004 evaluaban `WITH CHECK` por el id de la fila nueva, así que **el entrenador no podía insertar en ninguna tabla del editor**. Corregido en la 0010 |
| T-028 | `app_aceptar_invitacion` | 13 tests, los cinco resultados con su escenario; 7 mutaciones cazadas —reusar un token, ignorar o estirar el vencimiento, aceptar una revocada, robarle la ficha a quien ya la tiene, no marcarla usada, no distinguir vencida de inexistente—. Cada rechazo verifica el **efecto**, no sólo el texto devuelto |
| T-029 | Endpoints de estado del vínculo | 13 tests; 6 mutaciones cazadas —dejar que el atleta cambie su vínculo o invite, no revocar la anterior, permitir transiciones inválidas, invitar sobre lo archivado, token constante—. El token en claro se verifica ausente **sobre las respuestas** de las otras rutas |
| T-031 | Traducción del bloqueo silencioso | Resultó no ser silencioso: el ORM cuenta filas y levanta, así que era un **500** y no un falso éxito. Un manejador global —no un `if` por endpoint— lo traduce a 409 con su motivo. 5 tests, 5 mutaciones cazadas, incluida tapar cualquier error de base como si fuera el vínculo |
| T-030 | Endpoint de aceptación | 10 tests; 4 mutaciones cazadas. Los cinco resultados llegan como cinco respuestas distinguibles: **410 para la vencida y 404 para la inexistente**, que es el criterio 2 en el vocabulario que HTTP ya tiene. Sin email en el token no se inventa una identidad |
| T-032 | Fixtures de vínculos | Cuatro entrenadores sobre la misma persona —activo, pausado, archivado y uno nuevo—, cada uno con historial completo. Sin historial, "sobre lo archivado se lee todo" se verificaría sobre cero filas y pasaría siempre |
| T-033 | Recorrido de rutas: el eje del estado | 5 tests. Lleva un **mapa declarado** y no una regla ciega: cambiar estado tiene que seguir funcionando sobre lo archivado, o archivar sería irreversible. Una ruta de escritura nueva sin declarar hace fallar un test que la nombra |
| T-034 | Criterios 1 a 12 | 10 tests. Encontró que **archivar no invalidaba la invitación pendiente**, que la spec pedía y nunca se implementó: corregido en la migración 0012, dentro de la función de aceptación para que valga sin importar cómo se archivó |
| T-022 | Dominio: transiciones de estado | 8 tests escritos antes; 4 mutaciones —confundir los dos motivos de rechazo, colapsar pausado y archivado, dejar un agujero en la tabla, tratar pausado como archivado— caen 2 tests cada una |
| T-019 | Migración: `athlete.estado` | ida y vuelta sobre la base sembrada; forzando `is_active = false` el backfill mapea a `pausado` y no a `archivado`; un estado inventado lo rechaza el `CHECK` de la base |
| T-020 | Modelos y `docs/schema.sql` al día | `test_la_migracion_no_divergio_de_los_modelos`; el `CHECK` de la base se compara contra el enum del dominio |
| T-021 | Consumidores de `is_active` | 5 tests nuevos; sacándole el filtro al listado caen 2, cambiándolo por `!= archivado` cae 1, y quitando un valor del `CHECK` caen 3 |
| T-023 | Dominio: token de invitación | 9 tests escritos antes; 4 mutaciones —guardar el token en claro, estirar la vigencia, bajar la entropía, correr el borde del vencimiento— caen todas, y la del token en claro la caza el guardián de fuga |

## Pendientes

Una.

| ID | Tarea |
|---|---|
| T-035 | Documentación y backlog |

El orden no es libre. T-026 necesita la columna de T-019, T-027 necesita los
helpers de T-026, y T-031 no se puede escribir antes de que exista el bloqueo que
traduce. T-022 y T-023 eran de dominio puro y ya están; fueron el punto de entrada por
no depender de la base.

## Base de datos

**T-019 — Migración: `athlete.estado`.** Agregar `estado text NOT NULL` con
`CHECK (estado IN ('activo','pausado','archivado'))`. Backfill: `is_active = true`
a `'activo'`, `false` a `'pausado'`. Reconstruir `athlete_coach_idx` como
`WHERE estado = 'activo'`. Borrar `is_active`.

*Hecha cuando:* `upgrade` seguido de `downgrade` corre limpio sobre una base con
la planilla importada, y ninguna ficha queda en `'archivado'` — el backfill no
puede inventar un cierre que nadie pidió. Un `INSERT` con un estado inventado es
rechazado por la base, no por la aplicación.
*Bloquea a:* T-020, T-021, T-026.

**T-024 — Tabla `invitation`.** Columnas del plan §2. Índice parcial único
`(athlete_id) WHERE accepted_at IS NULL AND revoked_at IS NULL`.

*Hecha cuando:* insertar una segunda invitación pendiente para la misma ficha es
rechazado por la base. Insertar una segunda **después** de revocar la primera,
en la misma transacción, funciona. Ese par es el criterio 3 de la spec
garantizado por el esquema y no por que alguien se acuerde.
*Bloquea a:* T-025, T-028.

**T-025 — RLS de `invitation`.** Dos policies, con la misma forma que las de la
0004: el entrenador ve las invitaciones de sus fichas, a través de `athlete`. El
atleta no ve ninguna — cuando acepta todavía no tiene vínculo, y después no le
sirven para nada.

*Hecha cuando:* como rol de aplicación, el entrenador B no ve ni cuenta las
invitaciones de A. Sin contexto de tenant, la consulta falla ruidosamente en vez
de devolver cero filas, igual que todo lo demás desde la 0005.
*Bloquea a:* T-029.

**T-026 — Helpers `app_vinculo_escribible_<tabla>`.** Seis funciones
`SECURITY DEFINER`, `search_path` fijado, `EXECUTE` revocado de `PUBLIC`,
generadas del mismo mapa de cadenas que usan los `app_<rol>_ve_<tabla>` de la
0004.

*Hecha cuando:* para cada una de las seis tablas, la función devuelve falso
cuando el `athlete` al final de la cadena está archivado y verdadero en los otros
dos estados. Escribir la cadena a mano en vez de generarla del mapa es lo que
está prohibido acá: duplicada, se desincroniza.
*Bloquea a:* T-027.

**T-027 — Las 18 policies `RESTRICTIVE`.** Tres por tabla —`INSERT`, `UPDATE`,
`DELETE`— sobre `program`, `mesocycle`, `session`, `prescription`,
`prescribed_set` y `logged_set`. Las 18 policies de la 0004 **no se tocan**.
Sobre `athlete` no va ninguna: reactivar es un `UPDATE` sobre esa misma fila y la
policy lo bloquearía.

*Hecha cuando:* sobre un vínculo archivado, `SELECT` sigue trayendo el historial
completo, `INSERT` es rechazado con error, y `UPDATE` y `DELETE` afectan cero
filas. Los controles sobre un vínculo activo y uno pausado pasan los tres. Y
sacando **cualquiera** de las 18, un test nombra cuál falta: son 18 verificaciones
y no una.
*Bloquea a:* T-031, T-033.

**T-028 — `app_aceptar_invitacion`.** `SECURITY DEFINER`, misma forma que los
helpers. Busca por hash, verifica revocación, uso, vencimiento, resuelve el
`app_user`, comprueba que no sea ya atleta de ese entrenador, asocia y marca.
Devuelve cuál de los cinco casos ocurrió.

*Hecha cuando:* los cinco resultados —`aceptada`, `vencida`, `inexistente`,
`usada`, `ya_vinculado`— se producen cada uno con su escenario, y una segunda
llamada con el mismo token devuelve `usada` y no vuelve a asociar nada. Un token
que vence entre la emisión y la aceptación devuelve `vencida` contra el reloj
real, no contra uno simulado.
*Bloquea a:* T-030.

## Dominio

Sin base de datos y con los tests escritos primero (artículo IV).

**T-022 — Transiciones de estado.** Función pura: dado un estado y una acción,
devuelve el estado siguiente o el motivo del rechazo. Qué se puede hacer desde
dónde —pausar lo activo, reanudar lo pausado, archivar cualquiera de los dos,
reactivar lo archivado— y qué no.

*Hecha cuando:* los tests están escritos antes y cubren las transiciones válidas
y las que no lo son. Permitiendo una transición inválida cae al menos un test que
la nombra.

**T-023 — Token de invitación.** Generación con `secrets.token_urlsafe(32)`, su
hash, y el cálculo del vencimiento a partir del momento de emisión.

*Hecha cuando:* los tests están escritos antes; dos tokens generados seguidos no
coinciden; el hash es estable; y **el token en claro no aparece en nada que se
persista**. Este último se verifica buscando el token en la representación de lo
que se va a guardar, no leyendo el código.

## API

**T-021 — Consumidores de `is_active`.** Hoy es uno: el listado del entrenador
en `app/api/routes.py`. Pasa a filtrar `estado = 'activo'`.

*Hecha cuando:* el listado no trae ni pausados ni archivados, y `rg is_active`
sobre `backend/app` no devuelve nada.

**T-029 — Endpoints de estado del vínculo.** Generar invitación, pausar,
reanudar, archivar, reactivar. Todos del entrenador, todos bajo el router de
datos con el aislamiento que ya existe.

*Hecha cuando:* el token en claro se devuelve **una sola vez**, en la respuesta
de generación, y no hay ninguna ruta que lo vuelva a mostrar. Generar uno nuevo
deja el anterior inservible, verificado usándolo. El atleta no puede llamar a
ninguno de los cinco.

**T-030 — Endpoint de aceptación.** Cuelga del router de alta con
`require_identity_for_signup`, no del de datos: quien acepta todavía no tiene
vínculo y no hay contexto de tenant que setear.

*Hecha cuando:* los cinco resultados de T-028 se traducen a respuestas
distinguibles, y la de vencida se distingue de la de inexistente —lo pide la
spec—. Montarlo por error en el router de datos hace fallar un test, porque ahí
exigiría un `Active-Role` que quien acepta no puede tener.

**T-031 — Traducción del bloqueo silencioso.** Toda escritura que pueda caer
sobre un vínculo archivado comprueba filas afectadas y traduce el cero a un
rechazo explícito.

*Hecha cuando:* borrar una serie de un vínculo archivado devuelve un rechazo y no
un `204`. Se verifica rompiéndolo: sacando la comprobación de filas afectadas de
un endpoint, un test falla nombrando ese endpoint. Sin esa mitad, el test pasa
igual con el bug puesto, que es exactamente el modo de falla que esta tarea
existe para tapar.

## Tests

**T-032 — Fixtures de vínculos.** Un vínculo archivado con historial cargado,
uno pausado con historial, y una persona con cuatro entrenadores: tres archivados
y uno activo.

*Hecha cuando:* las usan T-033 y T-034 sin rearmar nada, y no dependen de la
planilla — el clon limpio y CI las tienen que poder construir.

**T-033 — Recorrido de rutas: el eje del estado.** Al recorrido de la 001 se le
agrega: toda ruta de escritura, sobre un vínculo archivado, no cambia el recurso.
Compara el estado antes y después, no la ausencia de excepción.

*Hecha cuando:* está parametrizado sobre las rutas que la app expone y no sobre
una lista escrita a mano, y agregar una ruta de escritura nueva rompe el test
hasta que alguien la declare. Verificado como T-016: sacando una policy de T-027,
falla nombrando la tabla.

**T-034 — Criterios 1 a 12.** Los doce de la spec, incluidos los cuatro nuevos
del `/clarify`.

*Hecha cuando:* los doce tienen test. El 9 —pausado no bloquea la escritura— es
el que protege la distinción entera: si pasa contra una implementación que trata
pausado y archivado igual, está mal escrito y hay que rehacerlo.

## Documentación

**T-035 — Documentación y backlog.** `README.md`, el backlog de `sdd/README.md`,
la tabla de cumplimiento de la constitución, y `docs/deploy.md` si la migración
agrega un paso.

*Hecha cuando:* la tabla de cumplimiento se auditó fila por fila contra lo que el
código hace, no contra lo que este plan dice que iba a hacer. En la 001 esa
auditoría encontró que las dos copias de la constitución habían divergido.
