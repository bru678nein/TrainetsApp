# Frontend

Todavía no inicializado. Cuando llegue el momento (feature 003):

```bash
npm create vite@latest . -- --template react-ts
npm install
npm i -D @tanstack/eslint-plugin-query prettier
npm i @tanstack/react-query react-router-dom
```

El cliente de la API no se escribe a mano: se genera desde el OpenAPI que ya
expone FastAPI en `/openapi.json`.

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.d.ts
```

Estructura prevista:

```
src/
├── api/          cliente generado + wrappers de react-query
├── features/
│   ├── athletes/
│   ├── program-editor/   ← el riesgo real del producto
│   └── workout/          ← lo que abre el atleta en el gimnasio
├── components/   UI compartida, sin lógica de negocio
└── lib/
```
