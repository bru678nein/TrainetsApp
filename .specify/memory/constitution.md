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

Toda tabla con datos de un entrenador lleva `coach_id` y está cubierta por Row
Level Security. Ninguna query de la capa de aplicación puede devolver datos de
otro tenant, ni siquiera por error de programación.

El aislamiento se testea: por cada endpoint que devuelve datos, existe un test
que verifica que el coach B no ve lo del coach A.

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

## Enmiendas

Se modifica con un commit que toque sólo este archivo, con el motivo en el
mensaje. Las specs anteriores no se reescriben retroactivamente: quedan como
registro de qué reglas regían cuando se decidieron.

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | (inicial) | Artículos I a X |
