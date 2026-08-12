# ADR 0002 — Los tests corren contra PostgreSQL, no contra SQLite

Fecha: 2026-08-07 · Estado: aceptado

## Contexto

El backend arrancó con modelos de SQLAlchemy escritos con tipos portables
(`Uuid`, `Numeric`) a propósito, para que la suite corriera en SQLite en memoria
y no hiciera falta levantar nada. Rápido de arrancar y cómodo en CI.

El problema apareció al escribir el esquema real. Buena parte de lo que hace que
este esquema sea correcto no existe en SQLite:

- Los `CHECK` constraints que impiden rangos invertidos y cargas ambiguas.
- `citext`, para que dos emails que difieren en mayúsculas sean el mismo.
- El índice funcional con `COALESCE` que hace únicos los nombres de ejercicio
  por coach, tratando el catálogo global como un tenant más.
- La vista `weekly_volume`.
- Row Level Security, que es cómo el proyecto aísla los datos de cada
  entrenador: en la base, no en cada endpoint.

Correr la suite en SQLite significaba que ninguna de esas cosas se ejercitaba
nunca. Los tests pasaban en verde sobre un motor que no era el de producción, lo
cual es peor que no tenerlos: dan confianza sin respaldarla.

Hubo además un caso concreto. Un `CHECK` sobre rangos de repeticiones rechazó 21
filas al importar la planilla real, y el motivo resultó ser una prescripción
compuesta en texto libre (`"8 a 12 + 2x 3 a 5"`) que ningún parser desambigua.
Ese constraint es el que encontró el problema. En SQLite no habría corrido.

## Opciones

**Seguir en SQLite y testear el esquema aparte.** Barato de mantener, pero
implica dos definiciones del esquema y la garantía de que van a divergir.

**SQLite para el dominio, Postgres sólo para lo que lo necesita.** Suena
razonable hasta que hay que decidir, test por test, de qué lado cae cada uno.
La frontera se vuelve una discusión permanente.

**Postgres para todo lo que toque la base.** Exige Docker corriendo y la suite
tarda segundos en vez de milisegundos.

## Decisión

Postgres real para todo test que toque la base. SQLite sale de la suite.

El esquema de la base de test lo crean **las migraciones de Alembic**, no
`Base.metadata.create_all()`. Si una migración está mal, los tests se enteran.
Hay además un test que compara los modelos contra la base migrada y falla si
divergieron.

Los tests del dominio (`app/domain/`) no tocan nada de esto y siguen corriendo
en milisegundos sin dependencias, que es justamente el punto de mantenerlos
libres de infraestructura.

Esa afirmación fue falsa durante un tiempo y nadie se enteró: `conftest.py`
importaba SQLAlchemy, Alembic y FastAPI a nivel de módulo, y pytest carga ese
archivo antes que cualquier test, así que un clon limpio no podía correr ni la
tabla de RPE. Los imports viven ahora adentro de las funciones que los usan.

Se comprueba corriendo los tests de dominio en un intérprete donde importar esas
tres librerías falla:

```python
import builtins
real = builtins.__import__
def bloqueado(nombre, *a, **k):
    if nombre.split(".")[0] in {"sqlalchemy", "alembic", "fastapi"}:
        raise ModuleNotFoundError(nombre)
    return real(nombre, *a, **k)
builtins.__import__ = bloqueado
import pytest
pytest.main(["tests/test_rpe.py", "tests/test_analytics.py", "tests/test_identity.py"])
```

Dos seguros:

- La suite exige que el nombre de la base termine en `_test` antes de borrar
  nada. Es lo único que separa un `pytest` con el `.env` equivocado de perder la
  base de desarrollo.
- Sin Postgres accesible, los tests de base se saltan con un mensaje explicativo
  en vez de fallar. Alguien que clona el repo ve los del dominio en verde.

## Consecuencias

**A favor:** los constraints, las extensiones, la vista y —cuando llegue— RLS se
ejercitan de verdad. La suite verifica lo que se deploya. Las migraciones quedan
testeadas por el solo hecho de correr los tests.

**En contra:** hace falta Docker para desarrollar. La suite pasó de
milisegundos a segundos. CI necesita un servicio de Postgres, con el costo de
arranque correspondiente. Un colaborador nuevo tiene una barrera más antes del
primer test en verde.

**Lo que no se resolvió:** los modelos siguen usando tipos portables aunque ya
no haga falta. No molestan, pero conviene no leerlos como una intención de
soportar otro motor: es sólo residuo de esta decisión.
