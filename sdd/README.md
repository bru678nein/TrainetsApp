# Cómo desarrollamos: Spec-Driven Development

La spec es el artefacto primario. El código es una salida regenerable a partir de
ella. Dicho al revés: si la spec y el código no coinciden, el que está mal es el
código.

## Instalación

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init . --integration claude
```

Deja los comandos, las reglas de contexto y la estructura de carpetas armadas.
Soporta cambiar de agente después sin rehacer nada.

## El ciclo

```
/constitution  →  /specify  →  /clarify  →  /plan  →  /tasks  →  /implement
    una vez        por feature                                    ↑
                                                          nada de código
                                                          antes de acá
```

| Comando | Produce | Pregunta que responde |
|---|---|---|
| `/constitution` | `.specify/memory/constitution.md` | ¿Qué reglas no se rompen nunca? |
| `/specify` | `specs/NNN-nombre/spec.md` | ¿Qué tiene que pasar, y para quién? |
| `/clarify` | spec sin `[NECESITA DEFINICIÓN]` | ¿Qué quedó ambiguo? |
| `/plan` | `specs/NNN-nombre/plan.md` | ¿Cómo se construye, con qué piezas? |
| `/tasks` | `specs/NNN-nombre/tasks.md` | ¿En qué pasos verificables se parte? |
| `/implement` | código y tests | — |

Regla de oro: **la spec dice qué y por qué, nunca cómo.** Si en una spec aparece
el nombre de una tabla, un endpoint o una librería, eso pertenece al plan.

## Estructura

```
.specify/memory/constitution.md      principios del proyecto
specs/
├── 001-identidad-y-aislamiento/
│   ├── spec.md                      qué y por qué
│   ├── plan.md                      cómo
│   ├── tasks.md                     pasos verificables
│   └── contracts/                   OpenAPI, esquemas, ejemplos
├── 002-editor-de-rutinas/
└── 003-invitaciones-y-vinculos/
```

Una feature por rama, nombrada igual que su carpeta.

## Backlog inicial

En orden. Cada una depende de la anterior.

| # | Feature | Estado | Por qué ahora |
|---|---|---|---|
| — | Migraciones con Alembic | hecho | Se resolvió antes de abrir el backlog, porque tener datos sin migraciones versionadas era deuda inmediata. Trajo la decisión de sacar SQLite de los tests: ver ADR 0002. |
| 001 | Identidad y aislamiento por tenant | **hecha**, 22 de 22 | Es el agujero más grande del backend actual y lo primero que mira un revisor. Todo lo demás se construye encima. |
| 002 | Editor de rutinas | **desbloqueada**, lista para `/plan` | El riesgo real del producto. Las tres definiciones se cerraron con evidencia: el presupuesto de interacción cronometrando la planilla, y la regla de progresión midiéndola — resultó que lo que progresa es el RIR y no la carga. |
| 003 | Invitaciones y ciclo de vida del vínculo | **en curso**, 7 de 17 (T-019 a T-025 hechas) | Salió de partir la 001. Habilita la 004, que es donde la Fase 0 puso el riesgo real del producto. El bloqueo de escritura sobre lo archivado está medido en `spike/restrictive.py`. |
| 004 | Vista de sesión y registro en el celular | | Es lo que el atleta usa todos los días. Mientras tanto lo cubre `backend/scripts/gen_app.py`. |
| 005 | Panel de análisis | **en curso**, 7 de 13 | El listado de atletas ya trae datos del backend. Faltan las tres vistas del panel y sus estados. |
| 006 | PWA con soporte offline | | En el gimnasio no hay señal. Sin esto, la 004 no se usa. |

La 001 nació cubriendo también las invitaciones y el archivado. El plan daba
bastante más de veinte tareas —la señal de que era más de una feature— y se
partió por urgencia: la 001 cierra el agujero de seguridad, la 003 es
funcionalidad de producto. El proveedor de auth está decidido en el ADR 0003.

## Cómo se escribe una buena spec

**Escribí para el entrenador, no para el ORM.** "El entrenador duplica la semana
3 sobre la 4 y ajusta las cargas un 5%" es una spec. "Se agrega un endpoint POST
a `/programs/{id}/weeks/duplicate`" es un plan.

**Toda spec declara lo que no hace.** Es requisito, no cortesía.

**Los criterios de aceptación se escriben como pruebas.** Si no sabés cómo
verificarlo, no está bien especificado.

**Las ambigüedades se marcan, no se suponen.** `[NECESITA DEFINICIÓN]` bloquea la
implementación.

## Errores típicos

**Specs que describen la implementación.** Si el agente puede escribir el código
directo desde la spec sin pensar, la spec era el código con otro formato.

**Specs enormes.** Si el plan da más de veinte tareas, era más de una feature.

**Saltear `/clarify`.** Es la fase más barata para descubrir que no sabías qué
querías. Un malentendido acá cuesta minutos; en `/implement` cuesta días.

**Dejar que la spec envejezca.** Cuando la implementación se desvía por un buen
motivo, se actualiza la spec en el mismo PR. Una spec desactualizada es peor que
no tenerla, porque miente con autoridad.

**Pedirle al agente que "arregle" un constraint que falla.** Ver artículo II: el
default es investigar el dato. Durante la migración de la planilla, un `CHECK`
sobre rangos de repeticiones rechazó 21 filas, y el motivo era que el original
decía `"8 a 12 + 2x 3 a 5"` — una prescripción compuesta que ningún parser
desambigua. Relajar el constraint habría escondido el problema.

---

Referencias: [Spec Kit](https://github.github.com/spec-kit/) ·
[Qué es SDD](https://github.github.com/spec-kit/concepts/sdd.html)
