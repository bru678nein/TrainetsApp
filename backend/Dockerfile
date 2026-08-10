# Imagen de producción. Python 3.11, el mismo que corre CI.
#
# Dos etapas para que la imagen final no cargue con el compilador: psycopg y
# cryptography traen wheels, pero si alguna vez falta una, el build necesita
# herramientas que no tienen por qué viajar a producción.
FROM python:3.11-slim AS build

# No escribir .pyc y no bufferear la salida: los logs de un contenedor se leen
# en vivo, y un stdout bufferizado los muestra recién cuando el proceso muere,
# que es justo cuando más falta hacen.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install -q -U pip && \
    /venv/bin/pip install -q -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"

# Sin privilegios. El contenedor no tiene por qué correr como root, y esto es la
# contraparte de la misma decisión que llevó al rol de aplicación en Postgres:
# nada corre con más permisos de los que necesita.
RUN useradd --create-home --uid 10001 app

COPY --from=build /venv /venv
WORKDIR /app
COPY --chown=app:app . .

USER app
EXPOSE 8000

# Las migraciones NO corren acá. Son un paso de release aparte, no algo que pase
# al arrancar cada instancia: con dos réplicas, dos procesos migrarían la misma
# base al mismo tiempo. Ver docs/deploy.md.
#
# El host es 0.0.0.0 porque adentro de un contenedor el default de uvicorn
# —127.0.0.1— sólo escucha desde adentro, y el balanceador no llega. Es la causa
# más común de "deployó bien y no responde".
# `sh -c` y no la forma exec, porque hace falta expandir $PORT: las plataformas
# gestionadas inyectan el puerto que quieren que escuches y enrutan hacia ahí.
# Con un puerto fijo, el deploy sale bien y el balanceador no encuentra a nadie.
# El 8000 queda de default para correrlo a mano.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
