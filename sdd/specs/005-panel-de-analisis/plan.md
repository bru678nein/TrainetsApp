# Plan — 005 Panel de análisis

Cómo se construye lo que la spec pide. La spec dice qué y por qué; acá aparecen
librerías, headers y archivos.

Es la primera feature con interfaz, así que la mitad de este plan es andamiaje
que se paga una vez y que la 004 hereda entero. Conviene tenerlo presente al
mirar el tamaño: no es el costo del panel, es el costo de que exista un frontend.

---

## 1. El andamiaje

**Vite + React + TypeScript**, como fijaron `docs/PLAN.md` §5 y el brief de
diseño. `npm` y no pnpm: no hay monorepo ni workspaces que justifiquen la
diferencia, y una herramienta menos que instalar en un clon limpio vale más que
la velocidad.

**React Router.** Dos pantallas no lo justifican; que la del atleta tenga URL
propia, sí. Un panel que no se puede mandar por link es un panel que se
comparte por captura, y la 004 va a necesitar rutas de todos modos.

**TanStack Query** para todo lo que venga del API. La spec pide estado vacío, de
carga y de error en cada pantalla —y dice que el vacío es el más importante—, o
sea tres máquinas de estado escritas a mano si no. Ahí es donde viven los bugs
que nadie ve: el spinner que no se apaga, el error que queda pegado después de
reintentar.

**Los gráficos, en dos tecnologías distintas y a propósito:**

- **Volumen y progresión: Recharts.** Son 17 semanas por 11 patrones, con ejes,
  tooltips y redimensionado. Eso es exactamente lo que una librería de gráficos
  hace bien y lo que a mano cuesta días.
- **Adherencia: HTML y CSS, sin librería.** Son barras proporcionales ordenadas
  por lo que peor cumple. Es la vista más importante de la feature —es la que
  contesta la pregunta— y es la que menos necesita una librería: son `div` con un
  ancho porcentual. Meter Recharts acá cuesta control sobre lo único que importa,
  que es el orden y el contraste entre el que cumple y el que no.

## 2. Autenticación: el SDK va en el navegador

El artículo VIII prohíbe manejar credenciales propias y prohíbe el SDK del
proveedor **en el backend**. El navegador es justamente donde ese SDK
corresponde: ahí vive la sesión, el login y el refresco.

**El token se pide en cada request, nunca se guarda.** Los tokens de sesión de
Clerk duran **60 segundos**. Guardarlo en un estado de React y reusarlo produce
401 intermitentes que aparecen sólo cuando el usuario deja la pestaña abierta un
minuto — el peor bug posible, porque no se reproduce mientras uno desarrolla.

**Una sola puerta al API.** Un envoltorio de `fetch` es el único lugar que arma
un request hacia `/api`, y es el que adjunta las dos cosas: el `Authorization` con
el token fresco y el header `Active-Role`.

Es la misma decisión que `tenant_session` en el backend, por el mismo motivo: si
cualquier componente puede llamar a `fetch` por su cuenta, alguien va a hacerlo
sin el header y va a recibir un `400` que no explica nada. Con una sola puerta,
olvidarse es imposible.

## 3. CORS, que es más que una línea

Hoy el backend **no tiene CORS**. Sin esto el navegador rechaza cada request
antes de que salga, y el error que muestra no menciona al servidor.

Dos detalles que lo hacen menos trivial de lo que parece:

**`Active-Role` tiene que estar en `allow_headers`.** Es un header custom, así
que dispara un preflight `OPTIONS`. Si no está declarado, el preflight falla y el
mensaje del navegador habla de CORS sin nombrar el header que falta — se pierde
una tarde buscando en el lugar equivocado.

**El origen permitido es el mismo valor que `AUTH_AUTHORIZED_PARTY`.** No es
coincidencia: los dos son el origen del frontend. Uno decide contra qué se compara
el claim `azp` y el otro a quién le contesta el navegador, y si se desincronizan
el síntoma son `401` que parecen de token. Se configuran desde la misma variable,
y un test afirma que no pueden divergir.

## 4. Las tres vistas

**Volumen por patrón, semana a semana.** Barras apiladas por patrón, con lo
prescrito como contorno y lo hecho como relleno. Consume `GET /athletes/{id}/volume`,
que ya existe.

**Adherencia desagregada.** Consume `GET /athletes/{id}/adherence`, que ya existe
y ya devuelve las tres preguntas —completitud, rango de repeticiones y desvío de
RIR—. Ordenada por lo que peor cumple, no alfabéticamente: el orden es la mitad
del diseño, porque es lo que pone el problema arriba sin que nadie lo busque.

Cada porcentaje viaja con su denominador, que es el criterio 3 de la spec.

**Progresión de carga.** No tiene endpoint. `load_progression` existe en
`app/domain/analytics.py`, está testeado y no lo expone nadie: es la única tarea
de backend de esta feature.

**Los estados vacíos** se construyen con los datos reales, que ya los tienen: hay
mesociclos sin una sola serie registrada y hay patrones con quince series en
total. No hay que inventarlos.

## 5. Qué se prueba, y qué no

Acá el estándar del repositorio baja **a propósito**, y conviene dejar escrito por
qué para que no parezca descuido.

Las mutaciones y los controles negativos valen donde una falla es **silenciosa**:
una policy que deja pasar una fila ajena, un `DELETE` que devuelve cero filas y un
`204`, un contexto de tenant que no se setea. Nada de eso se ve mirando.

Un gráfico mal dibujado se ve. No necesita un test que lo afirme.

**Se prueba:**

- El envoltorio de `fetch`, que adjunta las dos cabeceras. Sacando cualquiera de
  las dos tiene que caer un test que la nombre. Es el equivalente frontend del
  recorrido de rutas: protege una regla que se rompe por olvido.
- Que el token se pida por request y no se cachee, con un reloj falso.
- Los estados vacío, de carga y de error de cada vista. Son los que nadie mira a
  mano porque hay que provocarlos.
- El endpoint nuevo, con el estándar de siempre: tests primero y verificado
  rompiéndolo.

**No se prueba:** que un gráfico tenga las barras que corresponden, ni snapshots
de componentes. Un snapshot no verifica nada — se regenera cuando falla.

Vitest y Testing Library. `make check` corre las dos suites; CI llama a los mismos
targets, como el resto del repositorio.

## 6. Qué de diseño se decide acá y qué no

El riesgo que declara la spec: no hay componentes, ni tipografía, ni color.

**Se decide acá, porque el panel no puede existir sin ello:** escala tipográfica,
paleta —dos colores de dato, prescrito y hecho—, espaciado, y el estado vacío como
componente. Nada más.

**Se deja explícitamente abierto para la 004:** formularios, entrada numérica en
el celular, navegación de la app del atleta, tema oscuro. La 004 es mucho más
grande y decidir su lenguaje visual desde una pantalla de lectura sería decidirlo
sin el caso que importa.

## 7. Tareas

Continúan desde T-035 (feature 003).

1. **T-036** — Endpoint de progresión de carga, con tests primero.
2. **T-037** — CORS en el backend, con el origen atado a `AUTH_AUTHORIZED_PARTY`.
3. **T-038** — Andamiaje: Vite, TypeScript, ESLint, Vitest, y `make` que los corre.
4. **T-039** — Clerk en el navegador: login, sesión, pantalla de entrada.
5. **T-040** — El envoltorio de `fetch`: token fresco y las dos cabeceras.
6. **T-041** — Rutas y la carcasa de la aplicación.
7. **T-042** — Listado de atletas.
8. **T-043** — Estados vacío, de carga y de error, como componentes.
9. **T-044** — Vista de adherencia desagregada.
10. **T-045** — Vista de volumen por patrón.
11. **T-046** — Vista de progresión de carga.
12. **T-047** — La opción del entrenador: mostrarle la adherencia al atleta.
13. **T-048** — CI corre la suite del frontend.
14. **T-049** — README, backlog y captura del panel con datos reales.

Catorce. Las cinco primeras son andamiaje que la 004 hereda entera.

## 8. Deuda que este plan no paga

- **La analítica se calcula en Python trayendo todas las series a memoria.** Con
  un atleta y 17 semanas anda; la vista `weekly_volume` existe y no la consume
  nadie. Esta feature es la primera que lo va a ejercitar de verdad, y no lo
  arregla.
- **`GET /athletes/{id}/sessions` sigue sin paginación.**
- **El panel no produce los datos que muestra.** Vienen del importador. Cerrar el
  loop es la 002 y la 004.
- **Marcar una sesión como no esperada no existe**, así que el segundo número de
  adherencia no tiene de dónde salir todavía. El criterio 9 de la spec cubre esa
  ausencia: sin marcas, la fila no aparece.
- **Accesibilidad.** No hay auditoría de contraste ni de navegación por teclado, y
  un panel de gráficos es donde eso más falta. Queda declarado, no resuelto.
