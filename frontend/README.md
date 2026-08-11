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
