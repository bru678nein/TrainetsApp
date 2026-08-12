# Constitución del proyecto

Destino: `.specify/memory/constitution.md`

Los principios que ninguna spec puede contradecir. Cuando una spec choque contra
un artículo, gana el artículo — o se enmienda la constitución explícitamente,
dejando registro en el historial.

---

## Artículo I — El dominio no conoce la infraestructura

`app/domain/` contiene la lógica que no puede estar mal: tabla RPE, e1RM, volumen
semanal por patrón, adherencia, progresión de carga.

Reglas:

- No importa SQLAlchemy, FastAPI, Pydantic ni ningún driver de base de datos.
- Recibe y devuelve dataclasses o tipos primitivos.
- Se testea sin levantar base de datos, servidor ni fixtures de I/O.

Verificable: `grep -rE "sqlalchemy|fastapi|psycopg" app/domain/` debe devolver
vacío. Ponelo en CI.

## Artículo II — La base de datos rechaza lo imposible

Toda invariante expresable como constraint va en la base, no sólo en la
aplicación. Rangos coherentes, campos obligatorios, unicidad, exclusión mutua.

Motivo concreto: en la planilla que originó este proyecto, `pattern_code` era
opcional y 354 de 1.326 series quedaron sin clasificar, lo que inutilizó el
análisis de volumen durante meses sin que nadie se enterara. Un `CHECK` que
falla ruidosamente el primer día es más barato que un dato sucio descubierto al
sexto mes.

Corolario: cuando un constraint rechaza datos reales, **el default es investigar
el dato, no relajar el constraint**. Relajarlo requiere justificación escrita en
la spec.

## Artículo III — Aislamiento por tenant, sin excepciones

Ninguna query de la capa de aplicación puede devolver datos de otro tenant, ni
siquiera por error de programación. Toda tabla con datos de un entrenador está
cubierta por Row Level Security.

**Cada tabla declara cómo se llega a su tenant.** Puede ser una columna propia
—`athlete`, `program`— o un camino por claves foráneas: `logged_set` llega a su
entrenador por `prescribed_set → prescription → session → mesocycle → program`.
Denormalizar `coach_id` en todas las tablas es una opción, no un requisito, y
tiene su propio costo: una copia más que mantener consistente. Lo que no es
opcional es que el camino esté escrito y que la policy lo use.

Ninguna feature que exponga datos entra a `main` sin un test que verifique que
el entrenador B no ve lo del entrenador A, por cada endpoint que devuelva datos.
Desde la versión 1.2 eso **se verifica solo**: los recorridos se parametrizan
sobre las rutas que la app expone, no sobre una lista, así que un endpoint nuevo
rompe la suite hasta que alguien decida cómo se prueba. Ver "Cumplimiento".

## Artículo IV — Los tests del dominio van primero

Para `app/domain/`, el test se escribe antes que la implementación. Sin
excepciones: es la capa donde un bug es invisible y caro.

Para API y adaptadores, alcanza con que los tests existan antes del merge.

No se persigue cobertura total. Se persigue que todo cálculo que el entrenador
vaya a usar para decidir una carga esté cubierto.

## Artículo V — Toda spec declara lo que no hace

Una spec sin sección de "fuera de alcance" está incompleta. El alcance se define
tanto por lo que se excluye como por lo que se incluye.

Las ambigüedades se marcan `[NECESITA DEFINICIÓN]` y bloquean la implementación.
Suponer para no frenar está prohibido.

## Artículo VI — Simplicidad por default

Monolito hasta que duela. Sin microservicios, sin colas de mensajes, sin
Kubernetes, sin capas de abstracción "por si acaso".

Toda dependencia nueva se justifica en la spec: qué resuelve, qué alternativa de
la librería estándar se descartó y por qué.

Regla práctica: si una abstracción tiene una sola implementación y no hay una
segunda a la vista, no es una abstracción — es indirección.

## Artículo VII — La velocidad del entrenador es un requisito, no una aspiración

El competidor es Excel, y en Excel un entrenador arma una semana en minutos.

Toda feature del editor de rutinas declara su presupuesto de interacción: cuántos
clics y cuántas teclas cuesta la tarea. Si una tarea frecuente supera lo que
cuesta en una planilla, la feature no está terminada.

## Artículo VIII — Nada de auth propia

Autenticación mediante proveedor externo, verificando el JWT en el backend. No se
escriben hash de contraseñas, flujos de recuperación ni manejo de sesiones a mano.

## Artículo IX — Los datos de desarrollo son reales

El entorno de desarrollo se siembra importando planillas reales de entrenamiento,
nunca con datos inventados. Los datos reales traen los casos borde que los seeds
sintéticos esconden: prescripciones compuestas en texto libre, series de más de
12 reps fuera de la tabla RPE, cargas que cambian entre series.

## Artículo X — Cada artefacto es rastreable

Cada commit referencia su tarea; cada tarea, su plan; cada plan, su spec. Un
cambio que no se pueda rastrear hasta una spec aprobada no entra a `main`.

---

## Cumplimiento

Una constitución escrita en presente sobre cosas que todavía no pasan es peor
que no tenerla: quien la lee cree que el repo ya cumple. Esta tabla dice qué se
verifica hoy y con qué.

| Artículo | Cómo se verifica hoy |
|---|---|
| I — dominio sin infraestructura | `grep` en CI sobre `app/domain/`, y `test_el_dominio_no_importa_infraestructura`, que lee los `import` con AST en vez del texto — el grep marcaría un módulo que apenas nombre una librería en un comentario. Automático. |
| II — la base rechaza lo imposible | `tests/test_schema.py`: CHECKs, `citext`, índice funcional, vista. Automático. |
| III — aislamiento por tenant | **Cumplido.** RLS en las migraciones 0004 a 0012: **37 policies**. Diecinueve permisivas que deciden de quién es cada fila —dos por tabla, una sola en `invitation`, que el atleta no lee— y dieciocho restrictivas que impiden escribir bajo un vínculo archivado sin tocar la lectura, con `FORCE`, y un rol de aplicación que no es dueño ni superusuario. La capa HTTP resuelve el tenant en el router. Tres recorridos sobre *todas* las rutas de la app —sin credenciales, sin `Active-Role`, recurso ajeno— parametrizados sobre las rutas descubiertas y no sobre una lista, así que un endpoint nuevo rompe la suite hasta que alguien decida cómo se prueba. Automático. |
| IV — tests del dominio primero | Revisión humana. No es automatizable. |
| V — toda spec declara lo que no hace | Revisión humana al aprobar la spec. |
| VI — simplicidad por default | Revisión humana. |
| VII — velocidad del entrenador | **El umbral existe desde el 2026-08-10** y antes no: la Fase 0 cronometró al entrenador armando una semana en la planilla en unos 30 minutos —anotados 7 al principio y corregidos el 2026-08-11—, que cruzado con la composición real —4 sesiones, 27 prescripciones, 78 series— da 23 segundos por serie. Está escrito en la spec de la 002 como criterio falsable con cronómetro. Lo que falta es contra qué medirlo: no existe el editor. Revisión humana cuando exista. |
| VIII — nada de auth propia | Proveedor en el ADR 0003, librería en el 0004, cierre de sesión en el 0005 — delegado, sin estado de sesión propio. La firma la verifica PyJWT; lo nuestro es decidir con los claims ya decodificados (T-004 a T-006). Automático: `tests/test_tokens.py` firma con claves reales y prueba las falsificaciones. |
| IX — datos de desarrollo reales | `make seed` importa la planilla, y 7 de los 16 archivos de test la usan por la fixture `seeded`, que los saltea cuando falta. Los otros 9 construyen su propio escenario: los criterios 9 a 11 y los recorridos de rutas tienen que correr en CI, donde la planilla no existe. |
| X — cada artefacto es rastreable | Revisión humana. Desde la feature 001 los commits referencian su `T-NNN`; los anteriores no, y hay código en `main` sin spec previa. **La deuda vieja queda**, lo que cambió es que dejó de crecer. |

Lo que queda en deuda es el artículo X, donde la trazabilidad vieja no se
recupera y sólo dejó de crecer. El VII dejó de ser deuda a medias: el umbral ya
está medido y escrito, y lo que falta no es la definición sino el editor contra
el cual aplicarla. Las filas que
dicen "revisión humana" no son deuda: son cosas que no se automatizan, y decirlo
vale más que fingir un chequeo.

## Enmiendas

Se modifica con un commit que toque sólo este archivo, con el motivo en el
mensaje. Las specs anteriores no se reescriben retroactivamente: quedan como
registro de qué reglas regían cuando se decidieron.

Este archivo vive en `sdd/constitution.md`, y `.specify/memory/constitution.md`
es un symlink a él. Antes eran dos copias, y la regla de "un commit que toque
sólo este archivo" era literalmente incumplible; peor, se separaron de verdad —
la copia de `.specify/` llegó a decir que no había RLS ni tests de aislamiento
mucho después de que los hubiera. Un symlink no puede divergir.

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | (inicial) | Artículos I a X |
| 1.3 | 2026-08-09 | Se unifican las dos copias con un symlink, después de que divergieran de verdad. Se precisan los artículos I, VIII y IX: el primero tenía dos verificaciones y declaraba una, el segundo no mencionaba el cierre de sesión, y el tercero decía que los tests de API dependen de la planilla cuando la mayoría ya construye su escenario. |
| 1.2 | 2026-08-08 | Artículo III pasa de declarado a cumplido: RLS aplicado, y los recorridos de rutas se descubren en vez de listarse. Artículo VIII deja de decir "sin auth implementada". |
| 1.1 | 2026-08-07 | Artículo III: se corrigen dos afirmaciones falsas —no todas las tablas llevan `coach_id`, y los tests de aislamiento no existían— y se reformula como condición de merge. Se agrega la sección "Cumplimiento". |
