# AppWeb Lean

Plataforma de entrenamiento para coaches de fuerza. El entrenador prescribe
periodización por mesociclos, el atleta registra sus series desde el celular, y
el entrenador ve volumen por patrón, progresión de carga y adherencia.

## Arranque

```bash
make setup            # venv + dependencias + hooks
make db-up            # Postgres en Docker (crea coachapp y coachapp_test)
make migrate          # aplica las migraciones a coachapp
make db-app-password  # le pone contraseña al rol de aplicación (lo crea la 0003)
make seed             # importa data/planilla.xlsx
make api              # servidor en :8000, docs en /docs
make test             # tests (contra coachapp_test)
```

`make api` **no arranca sin configuración de auth**, y eso es a propósito: una
app que levanta contenta verificando tokens contra nada es peor que una que se
niega. Necesita un `backend/.env` con tres variables:

```
AUTH_ISSUER=...              # el `iss` que emite el proveedor
AUTH_AUTHORIZED_PARTY=...    # se compara contra `azp`, NO contra `aud`
AUTH_JWKS_URL=...            # <Frontend API URL>/.well-known/jwks.json
```

Son las únicas que la app lee de ese archivo: `DATABASE_URL` y las demás las pasa
el Makefile por línea de comando. Ver `docs/adr/0003` y `docs/adr/0004`.

## Estructura

| Carpeta | Qué hay |
|---|---|
| `backend/app/domain/` | Lógica pura: RPE, e1RM, volumen, adherencia. Sin I/O. |
| `backend/app/` | Modelos, esquemas, endpoints |
| `backend/migrations/` | Migraciones de Alembic. Fuente del esquema real. |
| `backend/importer/` | Carga planillas reales al esquema |
| `backend/scripts/` | Herramientas sueltas. Ver abajo. |
| `backend/tests/` | Dominio puro, esquema contra Postgres real, API, autenticación y composición de dependencias |
| `frontend/` | React + TypeScript (PWA). Vacío hasta la feature 004. |
| `data/` | Planillas reales. Ignorada por git salvo su README. |
| `sdd/` | Constitución, specs y flujo de trabajo |
| `.specify/` | Memoria de Spec Kit |
| `docs/` | `PLAN.md`, `schema.sql` de referencia y ADRs |
| `prompts/` | Prompts de arranque y de contexto para el proyecto |

### Herramientas

`backend/scripts/gen_app.py` genera una app web autocontenida —un solo `.html`—
desde una planilla. El atleta la abre en el celular sin instalar nada, registra
sus series y exporta lo cargado a CSV. Es el puente hasta que exista el frontend.

```bash
cd backend && .venv/bin/python scripts/gen_app.py ../data/planilla.xlsx rutina.html
```

Necesita `scripts/template.html`, que vive al lado.

## Base de datos

PostgreSQL 16+ y sólo PostgreSQL. El esquema lo definen los modelos de
SQLAlchemy en `backend/app/models.py`, y las migraciones de Alembic lo aplican.
Lo que el ORM no expresa —las extensiones `pgcrypto` y `citext`, el índice
funcional de `exercise`, la vista `weekly_volume`— está escrito a mano en la
migración correspondiente.

`docs/schema.sql` es documentación de referencia, no se aplica: quedó como el
registro de por qué el esquema es como es. Si tocás `models.py`, generá la
migración con `make migration m="..."`; hay un test que falla si divergen.

Los tests corren contra Postgres real, nunca contra SQLite. Los CHECK
constraints, `citext` y la vista no existen en SQLite, así que testear ahí daba
confianza falsa. Sin Postgres a mano, los tests de base se saltan con un mensaje
claro y los del dominio corren igual.

## Datos de desarrollo

El entorno se siembra con planillas reales de entrenamiento, no con datos
inventados (constitución, artículo IX). Los datos reales traen los casos borde
que los seeds sintéticos esconden: prescripciones compuestas en texto libre,
series de más de 12 repeticiones fuera de la tabla RPE, cargas que cambian entre
series del mismo ejercicio.

La planilla va en `data/planilla.xlsx` y **no se versiona**: contiene datos
personales de un atleta real (nombre, peso corporal, lesiones anotadas en los
comentarios). Está en `.gitignore` junto con el resto de `data/`.

```bash
make seed      # importa data/planilla.xlsx a la base
```

Sin ese archivo, los tests de API se saltan con un mensaje explicativo y los del
dominio corren igual — no hacen falta datos.

## Autenticación y aislamiento

El proveedor de identidad es externo y el backend sólo verifica el token
(constitución, artículo VIII). Quién sos sale del JWT; **desde qué rol estás
mirando** sale de un header `Active-Role`, obligatorio y sin default: una persona
puede ser entrenadora y, a la vez, atleta de otro, y adivinar el rol cuando falta
es lo que convierte eso en una vía de escape.

El aislamiento no depende de que cada endpoint se acuerde de filtrar. Está en la
base, con Row Level Security: dos policies por tabla, una por rol, y un rol de
aplicación que no es dueño de las tablas ni superusuario —las dos formas de
quedar exento de RLS—. Olvidarse del contexto no devuelve datos de más: da error.

Ver `sdd/specs/001-identidad-y-aislamiento/` para el diseño y el spike que lo
prueba rompiéndolo.

## Cómo se desarrolla

Spec-Driven Development. Nada de código sin spec aprobada. Ver `sdd/README.md`.

La regla de arquitectura que no se rompe: **`app/domain/` no importa
SQLAlchemy, FastAPI ni drivers de base de datos.** Lo verifica CI.
