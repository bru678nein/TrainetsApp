# 002 — Editor de rutinas

Estado: **bloqueada** por una definición pendiente · Rama: `002-editor-de-rutinas`

---

## Por qué

Hoy un entrenador no puede armar un programa. Puede entrar, ver a sus atletas y
crear una ficha; de ahí en adelante, la única forma de que exista una
planificación es el importador, que lee una planilla de Excel.

O sea que el producto todavía no reemplaza a la herramienta que vino a
reemplazar. La feature 001 cerró el agujero de seguridad y no agregó ni una
capacidad que el entrenador note.

Esta feature es la que decide si el producto existe. `docs/PLAN.md`, sección 6,
lo dice sin rodeos: es el 60% del esfuerzo de interfaz y donde estas apps se
ganan o se pierden. **El competidor no es TrainerStudio: es Excel**, donde un
entrenador arma una semana en minutos copiando y pegando bloques.

## Para quién

El **entrenador**, sentado, planificando. No carga un ejercicio: carga doce.
Repite estructuras entre semanas del mismo mesociclo y entre atletas distintos.
Viene de una herramienta donde el teclado alcanza para todo.

El atleta no participa de esta feature. Lo que ve él es la 004.

## Qué tiene que pasar

### Armar la estructura

El entrenador crea un programa para uno de sus atletas y lo llena: mesociclos,
semanas, sesiones dentro de cada semana, ejercicios dentro de cada sesión, y
series dentro de cada ejercicio.

Puede renombrar, reordenar y borrar en cualquiera de esos niveles. Puede dejar un
mesociclo a medio armar y seguir mañana.

### Prescribir una serie

Una serie prescrita dice cuántas repeticiones y con qué intensidad. Las tres
formas conviven y el entrenador usa las tres:

- **Carga absoluta**: 80 kg.
- **Carga relativa**: 75% del máximo.
- **Autorregulada**: sólo el RIR objetivo, y el peso lo elige el atleta ese día.

Repeticiones y RIR son **rangos**, no números: "10 a 15 repeticiones", "RIR 2-3".
Prescribir un valor exacto es el caso particular de un rango de uno.

Una serie no puede ser absoluta y relativa a la vez. La base ya lo impide; la
interfaz tiene que hacerlo evidente antes de que alguien lo intente.

### Duplicar, que es lo que decide todo

Es la razón por la que Excel gana hoy, y por eso no es una comodidad sino el
requisito central:

- **Duplicar una semana** sobre la siguiente, con todas sus sesiones y series.
- **Duplicar una sesión** dentro de la misma semana o hacia otra.
- **Duplicar un ejercicio** con su bloque de series.
- Al duplicar, que la copia salga **con la progresión que le corresponde por su
  posición en el bloque**, sin tocarla a mano.

#### La progresión la define el mesociclo, no la semana anterior

Esto se decidió midiendo la planilla, y lo medido corrigió la pregunta. Estaba
escrita como "por qué regla progresa **la carga**", y la carga casi no progresa:
en 100 series de ejercicio×mesociclo se queda igual el 60% de las veces, sube el
26% y baja el 14%. Las repeticiones no cambian nunca —104 de 104 iguales—.

Lo que progresa es el **RIR**, y baja en el 60% de los casos sin subir en
ninguno. Sus trayectorias sobre mesociclos de cuatro semanas:

| veces | RIR prescrito |
|---|---|
| 34 | 2 → 2 → 2 → 2 |
| 33 | 2 → 2 → 1 → 1 |
| 13 | 3 → 3 → 2 → 2 |
| 7 | 2 → 2 → 1 → 0 |

Sostiene dos semanas y baja un punto. **El patrón es posicional**: depende de
dónde cae la semana en el bloque, no de cuánto se movió la anterior. Una regla de
"progresá lo mismo que la vez pasada" reproduce las trayectorias planas y falla
en las escalonadas, que son la mitad.

Entonces: **el mesociclo declara su progresión una vez**, y duplicar una semana
la copia entera aplicando el valor que corresponde a la posición de destino. La
carga se copia igual —que es lo que pasa el 60% de las veces— y se edita a mano
cuando el entrenador quiere moverla.

Declararla una vez por bloque y no en cada duplicación es lo que hace cerrar el
presupuesto: son 27 prescripciones por semana, y una decisión por prescripción no
entra en 7 minutos.

Un límite honesto: esto es la programación de **un** entrenador. Que sea la forma
del producto y no su costumbre es una hipótesis. La spec la adopta porque es el
único entrenador que existe, no porque esté generalizada.

### El catálogo de ejercicios

El entrenador elige ejercicios de un catálogo. Hay ejercicios globales,
disponibles para todos, y puede crear los suyos.

Todo ejercicio declara su **patrón de movimiento**, y eso es obligatorio. No es
burocracia: sin patrón no hay análisis de volumen, que es la razón de ser del
producto. En la planilla original el patrón era opcional y 354 de 1.326 series
quedaron sin clasificar.

### Editar lo que ya se ejecutó

Un programa vivo se corrige: el atleta se lesiona, la semana salió mal, el
entrenador baja el volumen a mitad de camino. Eso tiene que poder hacerse.

**Lo que el atleta registró no se pierde nunca.** Borrar una serie prescrita que
ya tiene una registrada no borra el registro: la prescripción deja de estar y lo
que la persona hizo queda.

**Y la adherencia se compara contra lo que estaba prescrito cuando la ejecutó**,
no contra lo que quedó después. La razón es que la alternativa reescribe el
pasado: el entrenador sube el objetivo un mes más tarde y el 100% del atleta se
convierte en 60% sin que la persona haya hecho nada distinto. Una métrica que
cambia hacia atrás no sirve para decidir nada.

Tiene un costo y hay que decirlo: obliga a conservar la prescripción tal como era
en el momento de ejecutarse, no sólo la vigente. El plan decide cómo.

### La velocidad

**Definido por la Fase 0, el 2026-08-10.** El entrenador arma una semana completa
en la planilla en **unos 7 minutos**. Una semana real, medida sobre los datos
importados, son 4 sesiones, ~27 prescripciones y **78 series prescritas**.

El presupuesto es ese: **armar una semana equivalente acá tiene que costar menos
de 7 minutos, cronometrados de punta a punta.**

Está escrito en tiempo y no en clics a propósito, y conviene ser explícito sobre
por qué, porque el artículo VII pide clics y teclas. Lo que se midió fue el total,
no el costo por tarea dentro de la planilla; declarar un presupuesto de clics por
tarea exigiría un número que nadie tomó. Cronometrar la misma semana de punta a
punta compara exactamente lo que le importa al entrenador, es falsable con un
cronómetro y no depende de ponerse de acuerdo en qué cuenta como un clic.

De ahí salen dos consecuencias estructurales, que son la parte útil:

- **15,5 segundos por ejercicio y 5,4 segundos por serie**, incluyendo pensar la
  carga. Ninguna interacción por serie puede estar en el camino crítico: 78
  series a un clic cada una ya se comen buena parte del presupuesto sin haber
  leído ni decidido nada.
- **Duplicar-y-ajustar es la operación que hace cerrar el presupuesto**, no una
  comodidad. Ese ritmo en la planilla se logra copiando el bloque de la semana
  anterior; escribiéndolo es aritméticamente imposible. Un editor que lo trate
  como una función más entre otras pierde contra la planilla.

Contraste que ordena el resto: diez clics por ejercicio son 270 clics por semana,
cuatro minutos y medio de puro clic. Queda perdida antes de escribir código.

## Criterios de aceptación

Se escriben como pruebas. Los que dependen de una definición pendiente están
marcados.

1. Un entrenador arma un mesociclo completo —cuatro semanas, tres sesiones por
   semana, con ejercicios y series— y queda guardado tal como lo dejó.
2. Duplica la semana 1 sobre la 2 y la 2 tiene la misma estructura, con
   identidades propias: editar una no toca la otra.
3. Duplica una semana ajustando la carga, y todas las series con carga absoluta
   quedan modificadas según la regla acordada. `[depende de la definición de
   progresión]`
4. Prescribe una serie autorregulada, sin peso, y se guarda como tal en vez de
   quedar en cero.
5. Intenta prescribir carga absoluta y relativa a la vez, y la interfaz lo impide
   antes de enviarlo.
6. Crea un ejercicio sin patrón de movimiento y es rechazado.
7. Un entrenador no puede tocar el programa de un atleta de otro entrenador, por
   ninguna vía. Esto ya lo garantiza la 001; el criterio existe para que los
   endpoints nuevos queden cubiertos por los recorridos de rutas que ya
   verifican todas las rutas de la app.
8. Armar una semana desde cero cuesta menos que en la planilla.
   `[depende del presupuesto de interacción]`
9. Editar una semana que el atleta ya empezó a registrar se comporta según lo
   definido, sin perder trabajo del atleta. `[depende de la definición de
   edición sobre lo ejecutado]`

## Fuera de alcance

- **La vista del atleta.** Registrar series desde el celular es la 004. Esta
  feature construye lo que el atleta va a ver, no cómo lo ve.
- **El panel de análisis.** Volumen, progresión y adherencia ya se calculan y se
  sirven; presentarlos es la 005.
- **Invitaciones y vínculos.** Cómo un atleta reclama su ficha es la 003.
- **Plantillas y biblioteca de programas.** Guardar un mesociclo como plantilla
  para reusarlo con otros atletas es una feature aparte, y probablemente la
  siguiente en valor. Duplicar dentro de un programa sí entra; duplicar entre
  atletas, no.
- **Compartir programas entre entrenadores.**
- **Generación automática de rutinas**, con o sin IA. Este producto es
  profundidad en fuerza, y la profundidad la pone el entrenador.
- **Historial de versiones del programa.** Saber qué decía la prescripción antes
  de una edición es deseable y no entra acá, aunque la definición pendiente sobre
  editar lo ejecutado puede empujar en esa dirección.

## Cómo se relaciona con la constitución

- **Artículo VII** es el que manda en esta feature, y es el que la bloquea: el
  presupuesto de interacción es requisito, no aspiración.
- **Artículo II**: la carga polimórfica, los rangos y el patrón obligatorio ya
  están como constraints en la base. La interfaz los hace evidentes; no los
  reimplementa ni los relaja.
- **Artículo III**: los endpoints nuevos entran bajo el aislamiento que ya
  existe. Los recorridos de rutas de la 001 se parametrizan sobre las rutas que
  la app expone, así que cada endpoint que agregue esta feature rompe la suite
  hasta que alguien declare cómo se prueba. Eso es a propósito.
- **Artículo V**: esta spec ya no tiene `[NECESITA DEFINICIÓN]`. Las tres se
  cerraron con evidencia y no por consenso: el presupuesto de interacción salió de
  cronometrar la planilla, y la regla de progresión de medirla — la pregunta
  estaba mal formulada y apuntaba a la carga cuando lo que progresa es el RIR.

## Riesgos

**El primero es el de siempre y no es técnico.** Si armar una semana acá cuesta
más que en la planilla, el entrenador vuelve a la planilla el primer día malo. No
alcanza con que funcione: tiene que ser más rápido que lo que ya usa.

**El segundo es diseñar contra un número que no tenemos.** Se puede diseñar y
construir el editor sin la Fase 0, y descubrir al final que el presupuesto real
era la mitad. Rehacer sesenta horas de interfaz es caro; cronometrar al
entrenador cuesta diez.

**El tercero es la edición sobre lo ejecutado.** Es la clase de decisión que
parece un detalle al especificar y aparece como pérdida de datos en producción.
Por eso está marcada en vez de resuelta por default.

**Lo que no es un riesgo, aunque lo parezca:** el volumen de endpoints nuevos.
Son muchos, pero son CRUD sobre una jerarquía que ya está modelada y protegida.
El trabajo está en la interfaz, no en el backend.
