# Deploy

Este backend no se deploya con "push y listo", y el motivo es la decisión de la
tarea T-007: **la aplicación no se conecta como dueña de las tablas.** Eso obliga
a un orden que no es el habitual, y a un paso manual que se hace una sola vez.

Vale la pena porque es lo mismo que hace que el aislamiento funcione: el dueño de
una tabla está exento de Row Level Security salvo que se fuerce, y un
superusuario lo está siempre. Si la app se conecta con el rol equivocado, las
policies dejan de aplicar y nadie se entera.

## Las dos conexiones

Hay dos DSN distintos y no son intercambiables.

| | Quién | Para qué |
|---|---|---|
| **Admin** | El rol que da el proveedor, dueño de las tablas | Correr migraciones. Nada más. |
| **Aplicación** | `coachapp_app`, que crea la migración 0003 | El proceso de la API |

El rol de aplicación no es dueño de nada, no es superusuario y no tiene
`BYPASSRLS` — las tres formas de quedar exento. `tests/test_app_role.py` lo
verifica.

## Primer deploy, en orden

**1. Base de datos.** Cualquier Postgres 16+ gestionado. El proveedor te da un
DSN con un rol que es dueño; ese es el admin.

**2. Migraciones, con el DSN admin.**

```bash
DATABASE_URL="<admin>" python -m alembic upgrade head
```

Esto crea el esquema, el rol `coachapp_app`, y las 18 policies de RLS.

**3. Contraseña del rol de aplicación.** La migración lo crea **sin contraseña**,
a propósito: una contraseña versionada está en cada clon y en el historial para
siempre. Se la pone la infraestructura, una vez:

```bash
DATABASE_URL="<admin>" python -m scripts.set_app_password "<contraseña>"
```

Hasta que corras esto, el rol existe y no puede autenticarse. Es el estado
correcto, no un error.

**Cuidado: los roles son del cluster, no de la base.** `set_app_password.py`
cambia la contraseña de `coachapp_app` para **todas** las bases de ese servidor.
Ensayar el deploy contra una base descartable igual toca el rol compartido —
pasó ensayando esto mismo, y dejó el entorno de desarrollo sin poder conectarse
hasta correr `make db-app-password`. Si producción comparte servidor con algo
más, no es un detalle.

**4. Variables del proceso.**

```
DATABASE_URL=postgresql+psycopg://coachapp_app:<contraseña>@<host>/<base>
AUTH_ISSUER=<el `iss` que emite Clerk>
AUTH_AUTHORIZED_PARTY=<el origen del frontend, se compara contra `azp`>
AUTH_JWKS_URL=<Frontend API URL>/.well-known/jwks.json
```

Las tres de auth son obligatorias y no tienen default. **La aplicación se niega a
arrancar sin ellas**, y eso es deliberado: un deploy que levanta contento
verificando tokens contra nada es peor que uno que no levanta.

**5. Recién ahí, el contenedor.**

## Deploys siguientes

```
migraciones (DSN admin)  →  desplegar la imagen nueva
```

En ese orden, y son dos pasos separados.

**Las migraciones no corren al arrancar el contenedor.** Con dos réplicas,
arrancar es dos procesos migrando la misma base al mismo tiempo. Alembic toma un
lock y una de las dos espera, pero el arranque pasa a depender de una carrera que
nadie quiso. Es un paso de release.

## Lo que sale mal, y cómo se ve

**`current_setting("app.current_auth_user_id") no existe`** en cada request. La
app se está conectando como dueño o como superusuario y las variables de sesión
no se están seteando, o migró a `0003` y no a `head`. Es un error ruidoso a
propósito: la alternativa era devolver cero filas en silencio.

**Todo responde `401` con `credenciales inválidas`.** `AUTH_ISSUER` o
`AUTH_AUTHORIZED_PARTY` no coinciden con lo que emite Clerk. Ojo con el segundo:
se compara contra el claim `azp`, que es el origen del frontend, **no** contra
`aud`. Es el error más común de esta integración y por eso la variable se llama
como se llama.

**Todo responde `503`.** No se llega al JWKS. Mirá `AUTH_JWKS_URL` y si el
contenedor tiene salida a internet.

**Arranca y no responde.** Uvicorn escuchando en `127.0.0.1` en vez de `0.0.0.0`.
El `CMD` del Dockerfile ya lo resuelve; si lo sobreescribís, acordate.

**`permission denied for table ...` sobre una tabla nueva.** Falta el `GRANT`.
No debería pasar: la migración 0003 dejó `ALTER DEFAULT PRIVILEGES`, así que toda
tabla que cree una migración posterior queda accesible sola. Si pasa, es que
alguien creó la tabla con otro rol.

## Qué falta decidir

**La plataforma.** `docs/PLAN.md` sugiere Railway o Fly.io, las dos con Postgres
gestionado y deploy desde git. No está elegida.

**Backups.** Ninguno configurado. Con datos reales de entrenamiento adentro,
perderlos es perder meses de trabajo del entrenador, no un inconveniente.

**Dominio y HTTPS.** Los dos proveedores lo dan; no está hecho.

**Observabilidad.** Hoy son los logs del proceso y nada más. Alcanza para un
entrenador; no alcanza para veinte.
