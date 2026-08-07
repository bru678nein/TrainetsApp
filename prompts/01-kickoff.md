# Prompt de arranque de sesión

Para pegar en una sesión nueva de Claude Code, parado en la raíz del repo.
Ya no crea el proyecto: lo retoma.

---

Vamos a seguir trabajando en este proyecto. Antes de tocar nada, leé en este
orden: `README.md`, `sdd/constitution.md`, `sdd/README.md` y los ADR de
`docs/adr/`. Después mirá `backend/app/domain/` y `backend/tests/conftest.py`,
que son las dos piezas donde están las decisiones que más pesan.

## Qué es

Plataforma web para entrenadores de fuerza y powerlifting: prescriben
entrenamiento periodizado por mesociclos, el atleta registra sus series desde el
celular, y el entrenador ve volumen por patrón de movimiento, progresión de
carga y adherencia. El competidor real no es otra app: es Excel.

## Qué ya está

- **Dominio** (`app/domain/`): tabla RPE, e1RM, volumen semanal, adherencia,
  progresión. Sin dependencias de I/O, testeado aislado.
- **Esquema**: modelos SQLAlchemy 2.0 más migraciones de Alembic. Lo que el ORM
  no expresa —`pgcrypto`, `citext`, el índice funcional de `exercise`, la vista
  `weekly_volume`— está escrito a mano en la migración.
- **API**: endpoints de lectura de sesión y registro de series. Sin auth.
- **Importador**: carga planillas reales al esquema. 1.326 series de un atleta.
- **Tests**: 48. Los de base corren contra PostgreSQL real, nunca SQLite
  (ADR 0002). El esquema de test lo crean las migraciones, no `create_all`.
- **CI**: ruff, mypy, pytest y un guard que falla si `app/domain/` importa
  infraestructura.

## Qué falta, en orden

1. **Auth y aislamiento por tenant** — feature 001. Los endpoints todavía no
   filtran por coach y el RLS está diseñado pero sin cablear. Es el agujero más
   grande y lo primero que mira un revisor.
2. Editor de rutinas — el riesgo real del producto.
3. Vista del atleta en el celular, panel de análisis, PWA offline.

## Cómo trabajamos

Spec-Driven Development con Spec Kit: **Spec → Plan → Tasks → Implement**. Una
feature por rama, cada una con su carpeta en `specs/NNN-nombre/`.

- Nada de código antes de que la spec esté aprobada por mí.
- Los tests del dominio se escriben antes que la implementación (artículo IV).
- Si una decisión tiene más de una opción razonable, nombralas, decime cuál
  elegirías y por qué. No me des una lista de opciones equivalentes.
- Si algo de lo que te pido está mal, decímelo. No lo implementes igual.
- Cuando un constraint rechace datos reales, investigá el dato antes de tocar el
  constraint (artículo II).

## Restricciones

- Stack cerrado: FastAPI, PostgreSQL, React con TypeScript, PWA.
- Nada de auth propia. Proveedor externo, verificando el JWT en el backend.
- El dominio no puede depender de la infraestructura. Si una función de
  `app/domain/` necesita importar SQLAlchemy, está mal diseñada.
- Sin Kubernetes, sin microservicios, sin cola de mensajes.

## Antes de arrancar la 001

Su spec tiene tres `[NECESITA DEFINICIÓN]` que bloquean el plan. La que más pesa:
si un mismo email puede ser entrenador y atleta a la vez. Pasa seguido
—entrenadores que también se entrenan— y si la respuesta es sí, `coach` y
`athlete` no pueden seguir teniendo cada uno su `auth_user_id`: hay que separar
identidad de rol, y eso después es una migración fea.

Empezá corriendo `/clarify` sobre `sdd/specs/001-auth-y-tenancy/spec.md`.
