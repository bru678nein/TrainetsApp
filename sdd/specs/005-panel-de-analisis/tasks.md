# Tareas — 005 Panel de análisis

Del `plan.md` de esta carpeta. Cada tarea declara **cómo se sabe que está hecha**:
si no se puede verificar, está mal escrita.

Los commits referencian su tarea con `T-NNN` en el cuerpo (artículo X). La
numeración sigue desde T-035, que cerró la 003.

Es la primera feature con interfaz, así que el estándar de verificación **baja a
propósito** y el plan §5 dice por qué: mutar vale donde una falla es silenciosa, y
un gráfico mal dibujado se ve. Lo que sí lleva el tratamiento completo está
marcado tarea por tarea.

Estado: `pendiente` · `en curso` · `hecha`

---

## Hechas

| ID | Tarea | Verificado con |
|---|---|---|
| T-036 | Endpoint de progresión de carga | 3 tests de dominio escritos antes y 5 de API; 3 mutaciones —que la semana sin registro desaparezca, usarla en cero, devolver las semanas al revés— caen entre 2 y 4 tests cada una |
| T-038 | Andamiaje del frontend | un error de tipos hace salir `make check` con 1, y un test de frontend roto también; el único test que hay afirma que TypeScript, React, jsdom y Testing Library están conectados de verdad |
| T-039 | Clerk en el navegador | 3 tests sobre la puerta de sesión; montando los hijos fuera de ella caen 2 nombrándola. En el navegador real: el formulario de Clerk renderiza contra la instancia y salen **cero** requests al API sin sesión. No se completó un ingreso —requiere credenciales del dueño— |
| T-037 | CORS, atado a `AUTH_AUTHORIZED_PARTY` | 6 tests; sacando `Active-Role` de `allow_headers` cae 1 nombrándolo, abriendo el origen a `*` cae otro, y sin montar el middleware caen 3 |

## Pendientes

Nueve.

| ID | Tarea |
|---|---|
| T-040 | El envoltorio de `fetch` |
| T-041 | Rutas y carcasa |
| T-042 | Listado de atletas |
| T-043 | Estados vacío, de carga y de error |
| T-044 | Vista de adherencia desagregada |
| T-045 | Vista de volumen por patrón |
| T-046 | Vista de progresión de carga |
| T-047 | CI corre la suite del frontend |
| T-048 | Documentación y captura |

El orden importa poco salvo en dos puntos: T-040 necesita a T-039, y todas las
vistas necesitan a T-040. Las dos de backend ya están hechas — eran el punto de
entrada por no depender del frontend.

## Backend

**T-036 — Endpoint de progresión de carga.** Exponer `load_progression`, que ya
existe en `app/domain/analytics.py` y está testeado sin base de datos.

*Hecha cuando:* los tests están escritos antes; devuelve las semanas en que el
ejercicio se prescribió **incluidas aquellas sin nada registrado** —criterio 7 de
la spec, y es el caso que se pierde si uno arma la respuesta desde los registros
en vez de desde las prescripciones—; y el recorrido de rutas de la 001 lo cubre
solo, sin que nadie lo agregue a una lista, porque está parametrizado sobre las
rutas que la app expone. Si no lo cubre, el recorrido está roto y eso es lo que
hay que arreglar.
*Bloquea a:* T-046.

**T-037 — CORS.** Middleware con el origen del frontend, y `Active-Role` entre
los headers permitidos.

*Hecha cuando:* un preflight `OPTIONS` con `Active-Role` pasa, y **sacando ese
header de `allow_headers` cae un test que lo nombra** — sin eso el fallo aparece
recién en el navegador, con un mensaje que no menciona el header.

Y el origen sale de la misma configuración que `AUTH_AUTHORIZED_PARTY`, con un
test que afirma que no pueden divergir: son el mismo origen del frontend, y
desincronizados el síntoma es un `401` que parece problema de token.
*Bloquea a:* todo el frontend, en la práctica.

## Andamiaje

**T-038 — Vite, TypeScript, ESLint, Vitest.** Y los targets de `make` que los
corren, para que `make check` siga siendo el único comando que hay que saber.

*Hecha cuando:* `make check` corre las dos suites y falla si cualquiera falla. Un
error de tipos rompe el build —verificado introduciendo uno—, porque un
TypeScript que no chequea es peor que no tenerlo: da la confianza sin el chequeo.
*Bloquea a:* todo lo demás del frontend.

**T-039 — Clerk en el navegador.** Login, sesión y pantalla de entrada. El SDK
del proveedor va acá; el artículo VIII lo prohíbe en el backend, no en el cliente.

*Hecha cuando:* se entra contra la instancia real de Clerk, y **sin sesión la app
no llama a `/api` ni una vez** — verificado sobre los requests que salen, no
mirando la pantalla. Una app que pide datos antes de tener token produce 401 en
cada carga y enseña a ignorarlos.
*Bloquea a:* T-040.

**T-040 — El envoltorio de `fetch`.** El único lugar del frontend que arma un
request hacia `/api`. Adjunta el `Authorization` y el `Active-Role`.

*Hecha cuando:* **sacando cualquiera de las dos cabeceras cae un test que la
nombra.** Es el equivalente frontend del recorrido de rutas: protege una regla
que se rompe por olvido, no por error.

Y el token se pide en cada llamada, nunca se guarda: con un reloj falso, un token
cacheado sesenta y un segundos tiene que hacer fallar un test. Los de Clerk viven
60 segundos, y el bug de cachearlo sólo aparece con la pestaña abierta un rato —
o sea nunca mientras uno desarrolla.
*Bloquea a:* T-042 a T-046.

**T-041 — Rutas y carcasa.** Navegación y el esqueleto de la aplicación.

*Hecha cuando:* el panel de un atleta tiene URL propia y sobrevive a recargar la
página. Un panel que no se puede mandar por link se comparte por captura.

## Las vistas

**T-042 — Listado de atletas.** Los del entrenador que entró.

*Hecha cuando:* no aparecen ni pausados ni archivados. Lo garantiza el backend, y
el test acá existe para que se note si alguien decide filtrar en el cliente —que
es como se empieza a duplicar una regla de negocio en dos lados.

**T-043 — Estados vacío, de carga y de error.** Como componentes, no repetidos en
cada vista.

*Hecha cuando:* los tres son alcanzables en un test para cada vista, y **el vacío
dice por qué está vacío** —nadie registró todavía— en vez de mostrar ejes sin
nada adentro. La spec dice que el vacío es el más importante de los tres, y es el
único que nadie prueba a mano porque hay que provocarlo.

**T-044 — Adherencia desagregada.** Las tres preguntas de la spec, por patrón.

*Hecha cuando:* está ordenada por lo que peor cumple y no alfabéticamente, y cada
porcentaje muestra su denominador —criterio 3—. Con los datos reales importados,
la bisagra de cadera tiene que quedar arriba con su 72% sobre 226 series.

El criterio 2 —que un patrón al 100% y otro a la mitad se distingan sin leer
números— **no se automatiza y no se va a fingir que sí**: es revisión humana, y
decirlo vale más que un test que afirme colores.

**T-045 — Volumen por patrón, semana a semana.** Lo prescrito y lo hecho, juntos.

*Hecha cuando:* las dos series están presentes; un gráfico que muestre sólo lo
hecho no cumple, porque es lo que cualquier app de registro ya da y no es lo que
hace distinto a este producto.

**T-046 — Progresión de carga por ejercicio.** Consume T-036.

*Hecha cuando:* muestra las semanas prescritas sin registro como huecos y no como
ceros. Un cero dice "levantó nada"; un hueco dice "no hay dato", y son cosas
distintas.

## Cierre

**T-047 — CI corre la suite del frontend.** Con los mismos targets de `make` que
se usan en local.

*Hecha cuando:* CI falla si falla un test del frontend, verificado rompiendo uno a
propósito. Y **no reimplementa el comando**: llama al target. Esa deriva ya pasó
una vez en este repositorio.

**T-048 — Documentación y captura.** `README.md`, el backlog de `sdd/README.md`,
y la primera captura del panel con datos reales.

*Hecha cuando:* el README lleva la captura arriba, donde hoy hay una tabla de
texto, y dice qué muestra: 17 semanas reales, 11 patrones, y el patrón que se
saltea contra los que no. Es lo único de esta feature que cambia lo que alguien
concluye del proyecto en noventa segundos.

Y la captura **no puede tener el nombre del atleta**. Los datos son reales y
`data/` está en `.gitignore` por eso mismo; una captura lo devolvería al
repositorio por la puerta de atrás.
