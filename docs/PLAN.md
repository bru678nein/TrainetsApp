# Plataforma de coaching — plan de construcción

Contexto: portfolio primero, producto después. Un entrenador real desde el día 1. 20+ horas semanales.

---

## 1. El número incómodo, antes que nada

A 20 h/semana, algo cobrable son unas **13 semanas / 250 horas**. Presentable como portfolio, antes: **8 semanas / 160 horas**.

Del lado del dinero, la cuenta es la que es. Cobrando USD 20/mes por entrenador, diez entrenadores son USD 200/mes — y llegar a diez clientes pagando en un mercado con tres competidores establecidos toma la mayor parte de un año, con trabajo de venta que no es programar. Un solo mes de un puesto remoto paga más que ese año entero de SaaS.

**Conclusión operativa:** el retorno de este proyecto está en el portfolio, no en la facturación. Eso no lo hace menos valioso — lo hace un proyecto con un objetivo distinto al que parece. Construilo como si fuera producto (esa es la única forma de que quede bien), pero medí el éxito en entrevistas conseguidas, no en MRR.

Corolario práctico: cada decisión técnica que sirva para *demostrar criterio* vale más que una que ahorre dos días. Multi-tenancy con RLS, migraciones versionadas, tests de la lógica de dominio y CI son parte del entregable, no burocracia.

---

## 2. El ángulo

El mercado en español ya tiene TotalGains, Feast Fit y TrainerStudio: generalistas, entrenador de gimnasio comercial, rutinas + dietas + IA, desde ~€30/mes. No entrás por idioma ni por precio.

Entrás por **profundidad en fuerza**. Lo que ninguna de ellas modela en serio y la planilla de Nico sí:

- Autorregulación por RPE/RIR, no sólo series × reps × kg.
- Periodización real en mesociclos, con volumen por patrón de movimiento controlado semana a semana.
- e1RM estimado de cada serie y progresión de carga por ejercicio.
- Adherencia: prescripto contra ejecutado, que es la métrica que el entrenador mira para decidir la semana siguiente.

Público: entrenadores de fuerza y powerlifting, que hoy trabajan en planillas de Google Sheets exactamente como la que migramos. El competidor real no es TrainerStudio: **es Excel**, y Excel es gratis, rapidísimo para el entrenador y horrible para el atleta. Ahí está la grieta.

---

## 3. Fases

### Fase 0 — Validación sin código · 1 semana / 10 h

Sentarte con el entrenador y cronometrar cuánto tarda hoy en armar una semana de rutina en la planilla. Ese número es tu benchmark: si tu app tarda más, no la va a usar por más linda que sea. Anotá también las tres cosas que más lo irritan hoy.

No escribas una línea hasta tener eso. Es la fase que más gente se saltea y la que más proyectos mata.

### Fase 1 — MVP usable por un entrenador · 5 semanas / 100 h

- Auth (coach y atleta) y CRUD de atletas.
- Editor de rutina: mesociclos, semanas, sesiones, ejercicios, series prescritas.
- Catálogo de ejercicios con patrón de movimiento obligatorio.
- Vista del atleta en el celular: sesión del día, carga de reps/kg/RIR.
- Importador desde la planilla actual — ya tenés el parser escrito, reusalo.

Criterio de salida: el entrenador arma una semana entera sin tocar Excel y sin que vos intervengas.

### Fase 2 — Analítica y PWA · 3 semanas / 60 h

- Volumen semanal por patrón contra rango objetivo.
- Progresión de carga y e1RM por ejercicio.
- Adherencia por semana.
- PWA con service worker: el gimnasio suele no tener señal, y una app de entrenamiento que necesita conexión no se usa.

**Acá el proyecto ya sirve como portfolio.** Deploy público, README con capturas, datos de demo.

### Fase 3 — Multi-coach y cobro · 4 semanas / 80 h

- Onboarding self-service, planes por cantidad de atletas, Stripe o Mercado Pago.
- Panel de administración y límites por plan.

No empieces esta fase hasta que el primer entrenador lleve un mesociclo completo usándola.

---

## 4. Modelo de datos

Está en `schema.sql`, validado contra el parser de PostgreSQL. Cuatro decisiones que salen de los datos reales, no de la teoría:

**La unidad atómica es la serie, no el ejercicio.** En la planilla hay registros como `30kg x6 / 25kg x7 / 20kg x10`: la carga cambia entre series del mismo ejercicio. Si modelás a nivel ejercicio perdés eso y no podés calcular tonelaje ni e1RM.

**Prescripción y ejecución en tablas separadas.** En la planilla convivían en la misma fila y por eso la columna "Kg" a veces era el plan y a veces lo ejecutado. Separarlas es lo que hace posible medir adherencia.

**La carga prescrita es polimórfica.** Absoluta (80 kg), relativa (75% del 1RM) o autorregulada (sólo RIR objetivo, el peso lo elige el atleta). La planilla usaba las tres mezcladas. Hay un `CHECK` que impide prescribir absoluta y relativa a la vez.

**El patrón de movimiento es `NOT NULL`.** En la planilla era opcional y 354 de 1.326 series quedaron sin clasificar — sin patrón no hay análisis de volumen, que es la razón de ser del producto. Si el dato es imprescindible, la base lo exige.

Reps y RIR son rangos (`10 a 15`, `@2-3`), no escalares. Chequeado con constraints.

---

## 5. Stack

Tu stack, sin discusión: **FastAPI + PostgreSQL + React/TypeScript**. Es el que sabés y el que buscan. Las decisiones donde sí conviene tener opinión:

| Decisión | Recomendación | Por qué |
|---|---|---|
| ORM | SQLAlchemy 2.0 (estilo declarativo) + Alembic | SQLModel simplifica al principio y estorba en cuanto las queries se ponen serias. Las migraciones versionadas son parte de lo que mostrás. |
| Auth | Clerk — **decidido, ver ADR 0003** | Con backend FastAPI separado se integra verificando el JWT sin SDK. No escribas auth propia: no impresiona y consume dos semanas. |
| Aislamiento | RLS de Postgres + `coach_id` en toda tabla raíz | Es la parte que más criterio demuestra en una entrevista, y es más difícil de agregar después que de poner ahora. |
| Mobile | PWA, no React Native | Sin app stores, sin builds. Si el producto arranca, migrás. |
| Deploy | Railway o Fly.io | Postgres gestionado y deploy desde git. No pierdas tiempo con Kubernetes. |
| Tests | pytest sobre la lógica de dominio (e1RM, volumen, adherencia) | No busques cobertura total. Testeá los cálculos: son el corazón del producto y donde un bug es invisible. |

Nota de versiones: el ecosistema de auth se movió bastante; verificá el estado al momento de arrancar en vez de fiarte de esta tabla.

Se verificó en agosto de 2026 y el aviso valió la pena: `fastapi-users`, que esta tabla recomendaba como alternativa, había pasado a modo mantenimiento. La comparación completa —Clerk, Supabase Auth, Better Auth— está en el ADR 0003.

**Este archivo es el plan de arranque, no la fuente de verdad de las decisiones técnicas.** Cuando una decisión de acá se revisa, la revisión va a un ADR en `docs/adr/` y esta tabla queda como el razonamiento original. Ante una discrepancia, gana el ADR más reciente.

---

## 6. El riesgo real

No es técnico. Es el **editor de rutinas**.

Es el 60% del esfuerzo de UI y donde estas apps se ganan o se pierden. Un entrenador arma una semana en Excel en minutos, copiando y pegando bloques. Si tu editor lo obliga a diez clics por ejercicio, vuelve a la planilla el primer día malo — y va a tener razón.

Diseñá el editor pensando en duplicar: duplicar semana, duplicar sesión, duplicar ejercicio con progresión automática de carga. Entrada por teclado, sin mouse. Si conseguís que armar un mesociclo sea más rápido que en Excel, tenés producto. Si no, tenés un proyecto de portfolio muy prolijo — que, según la sección 1, tampoco es mal resultado.

---

## 7. Próximo paso concreto

Fase 0. Cronometrá al entrenador. Después de eso, el primer código que escribiría es el importador de la planilla a este esquema: te da datos reales para desarrollar contra ellos desde el día 1, en vez de seeds inventados, y el parser ya está hecho.
