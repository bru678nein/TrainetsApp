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

Esto crea el esquema, el rol `coachapp_app`, las funciones que cruzan el límite
del tenant, y 37 policies de RLS: 19 permisivas
que deciden de quién es cada fila, y 18 restrictivas que impiden escribir bajo un
vínculo archivado.

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

`AUTH_AUTHORIZED_PARTY` hace **dos cosas** y por eso tiene un solo valor: es
contra lo que se compara el claim `azp`, y es el único origen que CORS habilita.
Apuntado a otro lado que el frontend, falla dos veces y ninguna lo dice — el
preflight `OPTIONS` vuelve `400` y, si pasara, el token sería rechazado.

**El frontend es una aplicación aparte.** Se construye con `npm run build` y se
sirve como estático; sus variables (`VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_URL`)
se resuelven **en el build**, no al arrancar, así que cambiarlas exige construir
de nuevo.

Las tres de auth son obligatorias y no tienen default. **La aplicación se niega a
arrancar sin ellas**, y eso es deliberado: un deploy que levanta contento
verificando tokens contra nada es peor que uno que no levanta.

**5. Recién ahí, el contenedor.**

## Deploys siguientes

```
migraciones (DSN admin)  →  desplegar la imagen nueva
```

En ese orden, y son dos pasos separados. Invertirlos ya no es silencioso:
`/health/ready` compara la revisión de la base contra la que trae la imagen y
devuelve `503` mientras no coincidan.

**Las migraciones no corren al arrancar el contenedor.** Con dos réplicas,
arrancar es dos procesos migrando la misma base al mismo tiempo. Alembic toma un
lock y una de las dos espera, pero el arranque pasa a depender de una carrera que
nadie quiso. Es un paso de release.

## Lo que sale mal, y cómo se ve

**`/health/ready` devuelve `503` con `"status": "sin migrar"`.** La base está
en una revisión distinta de la que necesita la imagen desplegada, y la respuesta
trae las dos para que se sepa en qué dirección: `migracion` es lo que la base
tiene, `esperada` lo que el código pide.

Casi siempre es el orden: se desplegó la imagen sin correr las migraciones. Lo
contrario —una imagen vieja contra una base ya migrada— pasa cuando un rollback
del contenedor no vino con el `downgrade`.

Esta comparación existe porque su ausencia costó un deploy roto que se veía sano.
La ruta devolvía `ok` con el número de revisión y nada más, así que había que
saber de memoria cuál esperar; mientras tanto la base se quedó en `0005`, el
código siguió desplegándose hasta `0007`, y cada endpoint de datos devolvía 500
consultando una columna que todavía no existía.

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

**El healthcheck pasa y el dominio público devuelve "Application failed to
respond".** El puerto de destino del dominio no es el que el proceso escucha. El
`CMD` usa `$PORT`, que la plataforma inyecta, mientras que el `EXPOSE 8000` del
Dockerfile es lo que la plataforma mira para adivinar el destino cuando nadie se
lo dice. Los dos números salen de lugares distintos y no tienen por qué coincidir.

Distinguirlo de una app caída no requiere adivinar: si es el puerto, abrir el
dominio **no deja ninguna línea** en el log del contenedor, porque el request
nunca llega. El healthcheck no lo detecta porque va por dentro y no por el
dominio — es el único caso donde estar en verde no significa nada para un
visitante.

**`permission denied for table ...` sobre una tabla nueva.** Falta el `GRANT`.
No debería pasar: la migración 0003 dejó `ALTER DEFAULT PRIVILEGES`, así que toda
tabla que cree una migración posterior queda accesible sola. Si pasa, es que
alguien creó la tabla con otro rol.

## Qué falta decidir

**La plataforma.** Railway, desplegada. `railway.json` fija el builder y el
healthcheck; el resto es configuración del panel y no está versionada.

Lo que había que averiguar antes de comprometerse era si permitía `CREATE ROLE`,
porque sin eso la migración `0003` no corre y el aislamiento de T-007 no se puede
desplegar tal cual. **Lo permite**, verificado contra la instancia real.

**Backups.** Ninguno configurado. Con datos reales de entrenamiento adentro,
perderlos es perder meses de trabajo del entrenador, no un inconveniente.

**Dominio y HTTPS.** Los dos proveedores lo dan; no está hecho.

**Observabilidad.** Hoy son los logs del proceso y nada más. Alcanza para un
entrenador; no alcanza para veinte.
