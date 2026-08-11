# Frontend

Vite + React + TypeScript. La primera pantalla es el panel de análisis del
entrenador; la app del atleta llega después y es mucho más grande.

```bash
make front-dev     # servidor en :5173
make front-lint    # ESLint y tipos
make front-test    # Vitest
make check         # backend y frontend, lo mismo que corre CI
```

**El puerto 5173 no es negociable en desarrollo.** Es el valor que lleva
`AUTH_AUTHORIZED_PARTY` en el backend, que se compara contra el claim `azp` del
token y además es el origen que habilita CORS. Moverlo sin mover esa variable
falla dos veces con dos errores que parecen no tener relación: un `401` que se
lee como problema de token, y un rechazo del navegador que sólo habla de CORS.

El cliente del API no se escribe a mano: se genera desde el OpenAPI que expone
FastAPI.

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
```

## Probarlo de punta a punta

Tres terminales y un paso que no es obvio.

```bash
make db-up && make migrate && make seed    # base con la planilla real adentro
make api                                   # backend en :8000
make front-dev                             # frontend en :5173
```

**El paso que falta:** tu usuario de Clerk no existe en la base local. El
entrenador que crea el importador tiene `auth_user_id = 'seed-coach'`, así que
entrando con tu cuenta el aislamiento funciona perfecto y te muestra lo que te
corresponde — nada.

Sacá tu User ID del panel de Clerk (Users; empieza con `user_`) y apuntá los
datos sembrados a vos:

```bash
make db-claim SUB=user_2abc...
```

Después entrá en http://localhost:5173. Deberías ver un atleta, y adentro la
adherencia por patrón con bisagra de cadera arriba de todo al 72%.

Hay que repetirlo después de cada `make seed`, porque el importador vuelve a
escribir `seed-coach`.

## Cuando no anda

Cada capa falla con un código distinto, y eso es a propósito: el error dice dónde
mirar sin adivinar. Mirá el log de `make api`, no la consola del navegador.

| Lo que ves | Qué está mal |
|---|---|
| `OPTIONS … 400` | El origen no coincide. `AUTH_AUTHORIZED_PARTY` tiene que ser exactamente el origen del frontend, `http://localhost:5173`. |
| `GET … 503` | No se llega al JWKS. Probalo: `curl -o /dev/null -w '%{http_code}\n' "$AUTH_JWKS_URL"`. Un `000` es un host que no existe. |
| `GET … 401` | El token no valida. `AUTH_ISSUER` no coincide con el `iss` que emite Clerk. |
| `GET … 403` | El token está bien y tu identidad no es dueña de nada: falta `make db-claim`. |
| `200` y lista vacía | El `db-claim` corrió con un `SUB` que no es el tuyo. |

Las tres variables se leen **una vez, al arrancar**. Cambiar el `.env` con el
servidor prendido no hace nada: hay que cortar `make api` y volver a levantarlo.

## Estructura

```
src/
├── api/          cliente generado y el único envoltorio que llama al backend
├── components/   UI compartida, sin lógica de negocio
├── features/
│   └── analytics/    el panel del entrenador
└── lib/
```

## Qué se prueba acá

El estándar del backend —mutar la implementación y exigir que caiga un test con
nombre— vale donde una falla es **silenciosa**. Un gráfico mal dibujado se ve, y
no necesita un test que lo afirme.

Lo que sí lleva ese tratamiento es el envoltorio que habla con el API: adjunta
dos cabeceras, y olvidarse de una es exactamente el tipo de error que ningún
humano nota mirando la pantalla. También los estados vacío, de carga y de error,
que nadie prueba a mano porque hay que provocarlos.

No hay snapshots. Un snapshot no verifica nada: se regenera cuando falla.
