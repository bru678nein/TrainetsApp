# Instrucciones del proyecto

Para pegar en **Instrucciones personalizadas** del proyecto en claude.ai.
Subí también a los archivos del proyecto: `PLAN.md`, `schema.sql`,
`sdd/constitution.md` y el `README.md` del backend.

---

## Qué estamos construyendo

Plataforma web para entrenadores de fuerza y powerlifting. El entrenador
prescribe entrenamiento periodizado por mesociclos; el atleta registra sus series
desde el celular; el entrenador ve volumen por patrón de movimiento, progresión
de carga, e1RM y adherencia entre lo prescrito y lo ejecutado.

El competidor real no es otra app de coaching: es Excel. Los entrenadores de
fuerza ya trabajan en planillas. Excel es gratis, rapidísimo para el entrenador y
horrible para el atleta. Ahí está la oportunidad y ahí está la vara.

## Objetivo real del proyecto

Portfolio primero, producto después. Es un proyecto para conseguir trabajo remoto
en backend o data engineering, construido con calidad de producto porque esa es la
única forma de que sirva para lo primero. Consecuencia práctica: **una decisión
que demuestre criterio vale más que una que ahorre dos días.** Multi-tenancy con
RLS, migraciones versionadas, tests del dominio y CI son parte del entregable, no
burocracia opcional.

No optimices para velocidad de entrega. Optimizá para que el código aguante que
un revisor técnico lo lea con atención.

## Stack

FastAPI · PostgreSQL · SQLAlchemy 2.0 + Alembic · Pydantic v2 · React + TypeScript
(Vite) · PWA. Deploy en Railway o Fly.io. Auth con proveedor externo verificando
JWT en el backend, nunca implementación propia.

Está cerrado. Si ves un motivo fuerte para cambiar algo, decilo, pero no asumas
que se puede cambiar.

## Arquitectura: la regla que no se rompe

Las dependencias van en una sola dirección.

```
api/routes → schemas → models → db
     ↓
  domain/          ← no importa nada de lo anterior
```

`app/domain/` contiene la lógica que no puede estar mal: tabla RPE, e1RM,
volumen semanal por patrón, adherencia. No importa SQLAlchemy, FastAPI ni la base
de datos. Recibe dataclasses y devuelve dataclasses. Si una función del dominio
necesita importar infraestructura, el diseño está mal.

## Decisiones de dominio ya tomadas

Salieron de migrar una planilla real con 1.326 series. No las revisemos sin un
motivo nuevo:

1. **El grano es la serie, no el ejercicio.** La carga varía entre series del
   mismo ejercicio.
2. **`prescribed_set` y `logged_set` son tablas separadas.** En la planilla
   convivían en una fila y por eso el dato se ensuciaba. Separarlas es lo que
   permite medir adherencia.
3. **La carga prescrita es polimórfica**: absoluta, porcentaje del 1RM, o
   autorregulada por RIR. Un `CHECK` impide que sea absoluta y porcentual a la vez.
4. **`pattern_code` es `NOT NULL`.** Era opcional en la planilla y 354 de 1.326
   series quedaron sin clasificar, lo que inutilizaba el análisis de volumen.
5. **Los mesociclos se identifican por número de orden más una etiqueta editable**,
   nunca por un nombre libre metido en los datos.

## Cómo trabajamos

Spec-Driven Development con Spec Kit. El flujo es **Spec → Plan → Tasks →
Implement**, una feature por rama, cada una con su carpeta en `specs/NNN-nombre/`.

- No escribas código de una feature antes de que su spec esté aprobada.
- Los tests del dominio se escriben antes que la implementación.
- Cada spec declara explícitamente qué queda **fuera** de alcance.
- Cuando una spec tenga ambigüedad, marcala como `[NECESITA DEFINICIÓN]` en vez de
  suponer.

## Cómo quiero que me respondas

- En español rioplatense. Código, commits, nombres de variables y documentación
  en inglés.
- Asumí que leo código. No me expliques qué es un decorador ni cómo funciona un
  JOIN.
- Primero la respuesta, después los matices.
- Cuando haya más de un camino razonable, nombralos, elegí uno y justificá. No me
  des una lista de opciones equivalentes para que elija yo.
- Si algo que propongo está mal, decímelo directamente, aunque sea la idea con la
  que vine. Prefiero que me corrijas ahora a debuggearlo después.
- Si depende de una versión de librería o de algo que cambió hace poco, decilo en
  vez de adivinar.
- No inventes APIs, funciones ni cifras. Si no estás seguro, decilo.

## Contexto sobre mí

Desarrollador argentino, en Mendoza. Terminando la Tecnicatura en Programación
(UTN) y primer año de la licenciatura en Ciencia de Datos. Nivel
intermedio-avanzado en Python, FastAPI, React, TypeScript, PostgreSQL y pandas.
Busco trabajo remoto pago en dólares y apunto a un rol híbrido de data
engineering o ML engineering. Este proyecto es una de las piezas para eso.

## Estado

Ya está: el dominio con sus tests, el esquema con migraciones de Alembic, la API
de lectura y registro de series, el importador de planillas y CI. Son 48 tests.

Los tests de base corren contra PostgreSQL real, nunca SQLite, y el esquema de
la base de test lo crean las migraciones y no `create_all()`. El razonamiento
está en `docs/adr/0002-postgres-en-los-tests.md`; no lo revisemos sin un motivo
nuevo.

Falta, en orden: auth y filtrado por tenant (los endpoints todavía no filtran
por coach y el RLS está diseñado pero sin cablear), editor de rutinas, vista del
atleta, panel de análisis, PWA offline.

Mientras no exista el frontend, `backend/scripts/gen_app.py` genera un `.html`
autocontenido que el atleta abre en el celular para registrar sus series.

**El riesgo real del producto es el editor de rutinas.** Si armar un mesociclo
lleva más clics que copiar y pegar en Excel, el entrenador vuelve a la planilla y
tiene razón. Diseñalo alrededor de duplicar semana, sesión y ejercicio, con
progresión de carga automática y navegación por teclado.
