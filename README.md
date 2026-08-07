# AppWeb Lean

Plataforma de entrenamiento para coaches de fuerza. El entrenador prescribe
periodización por mesociclos, el atleta registra sus series desde el celular, y
el entrenador ve volumen por patrón, progresión de carga y adherencia.

## Arranque

```bash
make setup     # venv + dependencias + hooks
make db-up     # Postgres en Docker
make test      # tests
make api       # servidor en :8000, docs en /docs
```

## Estructura

| Carpeta | Qué hay |
|---|---|
| `backend/app/domain/` | Lógica pura: RPE, e1RM, volumen, adherencia. Sin I/O. |
| `backend/app/` | Modelos, esquemas, endpoints |
| `backend/importer/` | Carga planillas reales al esquema |
| `frontend/` | React + TypeScript (PWA) |
| `sdd/` | Constitución, specs y flujo de trabajo |
| `docs/` | Decisiones de arquitectura |

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

## Cómo se desarrolla

Spec-Driven Development. Nada de código sin spec aprobada. Ver `sdd/README.md`.

La regla de arquitectura que no se rompe: **`app/domain/` no importa
SQLAlchemy, FastAPI ni drivers de base de datos.** Lo verifica CI.
