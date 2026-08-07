# Prompt de arranque

Para pegar en una sesión nueva de Claude Code, parado en el repo vacío.
Adjuntá `PLAN.md`, `schema.sql` y la carpeta `backend/` antes de mandarlo.

---

Vamos a arrancar un proyecto desde cero. Antes de escribir código, leé los tres
adjuntos completos: `PLAN.md` tiene el análisis de negocio y las decisiones de
dominio, `schema.sql` el modelo de datos validado, y `backend/` un esqueleto
funcional de la fase 1 con 45 tests en verde.

## Qué es

Una plataforma web para entrenadores de fuerza y powerlifting: prescriben
entrenamiento periodizado por mesociclos, el atleta registra sus series desde el
celular, y el entrenador ve volumen por patrón de movimiento, progresión de carga
y adherencia. El competidor real no es otra app: es Excel.

## Estado actual

El backend de la fase 1 ya existe y funciona:

- `app/domain/` — lógica pura (tabla RPE, e1RM, volumen, adherencia). No importa
  SQLAlchemy ni FastAPI. Se testea sin base de datos.
- `app/models.py` — SQLAlchemy 2.0, espejo de `schema.sql`.
- `app/api/routes.py` — endpoints de lectura y registro de series.
- `importer/` — carga una planilla real (1.326 series de un atleta) al esquema.
- `tests/` — 45 tests: dominio puro más end-to-end sobre esos datos reales.

## Qué necesito de vos en esta sesión

1. Leé el código existente y decime si hay algo que rediseñarías **antes** de
   construir encima. Prefiero que me discutas ahora una decisión que arrastrarla
   tres meses. Sé concreto: qué cambiarías y qué costo tiene no cambiarlo.
2. Instalá y configurá Spec Kit para trabajar con Spec-Driven Development:
   `uvx --from git+https://github.com/github/spec-kit.git specify init . --integration claude`
3. Escribí `.specify/memory/constitution.md` con los principios del proyecto,
   tomando como base `sdd/constitution.md` que te paso aparte. No lo copies
   textual: adaptalo a lo que veas en el código real.
4. Cuando eso esté, arrancamos la primera feature: **auth y aislamiento por
   tenant**, que es el agujero más grande que tiene hoy el backend.

## Cómo quiero que trabajes

- Una feature por rama, con su carpeta en `specs/NNN-nombre/`.
- Nada de código antes de que la spec esté aprobada por mí.
- Los tests del dominio se escriben antes que la implementación. En la capa de
  API alcanza con que existan antes del merge.
- Si una decisión tiene más de una opción razonable, nombralas, decime cuál
  elegirías y por qué. No me des una lista de opciones equivalentes.
- Si algo de lo que te pido está mal, decímelo. No lo implementes igual.

## Restricciones

- Stack cerrado: FastAPI, PostgreSQL, React con TypeScript, PWA. No propongas
  cambiarlo salvo que tengas un argumento fuerte.
- Nada de auth propia. Proveedor externo, verificando el JWT en el backend.
- El dominio no puede depender de la infraestructura. Si una función de
  `app/domain/` necesita importar SQLAlchemy, está mal diseñada.
- Sin Kubernetes, sin microservicios, sin cola de mensajes. Es un monolito y va a
  seguir siendo un monolito por bastante tiempo.

Empezá por el punto 1: leé el código y decime qué está mal.
