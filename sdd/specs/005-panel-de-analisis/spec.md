# 005 — Panel de análisis

Estado: borrador · Rama: `005-panel-de-analisis`

Depende de la 001, que ya aísla los datos, y del dominio de analítica, que ya
está escrito y testeado. Es la primera feature con interfaz.

---

## Por qué

El entrenador prescribe y hoy no sabe qué pasó. La planilla no se lo dice: el
atleta no la usa, así que no hay nada que mirar. Esa es la razón por la que este
panel existe, y también la razón por la que hoy no tendría datos — la 004 es la
que los produce.

Pero hay una razón más específica, y salió de mirar los datos reales.

Sobre las 17 semanas importadas, la adherencia global es **90%** —1.199 de 1.326
series—. Es un número que tranquiliza. Adentro de ese número, el atleta cumple al
99% en rodilla dominante, al 98% en empuje horizontal, al 96% en tracción
horizontal, y al **72%** en bisagra de cadera: 163 de 226 series.

No es que falte a entrenar. Sólo 2 de 68 sesiones quedaron enteras sin registrar.
Va, hace todo lo demás completo, y se saltea sistemáticamente un cuarto del
trabajo de isquios.

Eso es exactamente lo que un entrenador necesita saber y exactamente lo que un
número solo esconde. El panel existe para que esa pregunta se conteste sin
exportar nada a otro lado.

## Para quién

- **Entrenador**: mira si el plan que armó se está cumpliendo, y dónde no.
- **Atleta**: `[NECESITA DEFINICIÓN]`, abajo.

## Qué tiene que pasar

### Todo se compara contra el plan

Ningún gráfico muestra sólo lo que el atleta hizo. Muestra lo prescrito y lo
hecho, juntos.

Es lo único que este producto puede hacer y una app de registro genérica no: hay
un plan contra el cual comparar. Un gráfico de volumen sin la línea de lo
planificado es un gráfico que cualquier otra herramienta ya da.

### La adherencia son tres preguntas, no un número

Se responden por separado porque fallan por separado:

- **¿Hizo la serie?**
- **¿Le pegó al rango de repeticiones prescrito?**
- **¿Entrenó a la intensidad prescrita?** —el desvío contra el RIR pedido.

Un atleta que cumple el 100% de las series pero sistemáticamente dos puntos de
RIR por debajo del esfuerzo pedido está entrenando liviano y se ve perfecto. Es
el caso que un promedio único vuelve invisible.

### Toda serie prescrita cuenta

Si una serie estaba prescrita y no se registró, no se hizo. No hay umbral, no hay
sesión que se descarte, no hay heurística.

La razón no es la simplicidad: es que con los datos solos, **"no fue a entrenar"
y "fue y no registró nada" son indistinguibles**. Cualquier regla que las separe
está inventando información que no existe. Medido sobre las 17 semanas reales,
descartar las sesiones sin nada registrado mueve la adherencia de bisagra de
cadera de 72% a 74% — dos puntos, a cambio de una definición que no se puede
sostener con evidencia.

### Lo excluido se muestra, nunca se descuenta

Un atleta lesionado dos semanas se ve igual que uno que abandonó, y esa
información sólo existe en la cabeza del entrenador. Va a poder marcar una sesión
como **no esperada** — pero marcarla es escribir sobre el plan, no mirar el
análisis, así que no vive acá: ver más abajo, en Depende de.

Lo que sí decide esta spec es qué hace el panel con esas marcas, y es la parte que
importa: **nunca reemplazan el número, lo acompañan.**

> **72%** sobre todo lo prescrito · **81%** excluyendo 4 sesiones no esperadas

Los dos, siempre, y cuántas se excluyeron. Un denominador que el entrenador puede
mover es un número que deja de compararse contra sí mismo, y el modo de falla no
es la mala fe: es excluir una semana mala porque la persona venía con un momento
difícil. Eso es exactamente cómo una métrica se vuelve decorativa. Con los dos
números a la vista, ajustar sigue siendo posible y deja de ser invisible —y
cuánto se excluyó dice algo por sí solo: quince sesiones de sesenta y ocho es un
dato sobre el plan, no sobre el atleta.

### Un porcentaje sin su denominador miente

Todo porcentaje se muestra con la cantidad de series sobre la que se calculó.

No es prolijidad. Al preparar esta spec, "pliometría 0%" apareció como el titular
más fuerte del panel. El número era correcto: cero de quince. Pero quince series
concentradas en la última semana del programa no alcanzan para concluir nada
sobre una persona, y presentado como titular parecía una conducta.

Los patrones con pocas series se muestran; no encabezan.

### Lo que hay que poder mirar

- **Volumen por patrón de movimiento, semana a semana.** Es el eje central del
  producto: es donde se ve la forma de la periodización y dónde se despegó de lo
  planificado.
- **Adherencia**, con las tres preguntas de arriba, desagregada por patrón. Sin
  desagregar no sirve: el promedio es justo lo que tapa el problema.
- **Progresión de carga por ejercicio.** Es donde el entrenador vive. La pregunta
  es si la sentadilla sube, no cuántos kilos se movieron en total.

### La unidad es el mesociclo

El entrenador piensa en bloques, no en rangos de fechas. Entrar al panel muestra
un mesociclo, no un calendario que hay que configurar antes de ver algo.

### Los estados vacíos importan más que los llenos

Hoy hay un solo atleta y hay bloques sin una sola serie registrada. El panel
tiene que verse deliberado con pocos datos, y decir **por qué** está vacío —nadie
registró todavía— en vez de mostrar ejes sin nada adentro.

## Criterios de aceptación

Se escriben como pruebas.

1. Un mesociclo con series prescritas y ninguna registrada muestra el plan y dice
   que no hay registros, en vez de un panel vacío o un cero.
2. Un patrón donde el atleta cumplió todas las series y otro donde cumplió la
   mitad se distinguen a simple vista, sin leer números.
3. Una sesión entera sin registrar baja la adherencia igual que una serie
   salteada: no hay sesión que se descarte. Y un patrón con pocas series muestra
   su denominador y no encabeza la pantalla, aunque su porcentaje sea el peor.
4. Un atleta que registró todas sus series dos puntos de RIR por debajo de lo
   prescrito aparece señalado, aunque su completitud sea 100%.
5. El entrenador no puede ver el panel de un atleta de otro entrenador. Lo
   garantiza la 001; el criterio existe para que se rompa si alguien lo saltea.
6. Sobre un vínculo archivado, el panel se lee completo y no se puede modificar
   nada. Depende de la 003.
7. La progresión de carga de un ejercicio muestra las semanas en las que se
   prescribió, incluidas aquellas en las que no se registró nada.
8. Con sesiones marcadas como no esperadas, el panel muestra **las dos**
   adherencias y cuántas sesiones se excluyeron. Nunca sólo la ajustada.
9. Sin ninguna sesión marcada, el panel no muestra un segundo número vacío ni un
   "0 excluidas": la fila no existe hasta que exista una marca.

## Fuera de alcance

- **Editar cualquier cosa, incluido marcar una sesión como no esperada.** Este
  panel se lee. Prescribir es la 002, registrar es la 004, y marcar es una
  escritura sobre el plan — el panel consume esas marcas y no las produce.
- **Exportar.** Ni CSV ni PDF. Si el entrenador necesita sacar los datos para
  responder su pregunta, el panel no la respondió.
- **Comparar atletas entre sí.** El plan de cada uno es distinto y la comparación
  invita a conclusiones que los datos no sostienen.
- **Predicciones, proyecciones de 1RM a futuro o recomendaciones automáticas.**
  Este producto le da criterio al entrenador, no lo reemplaza.
- **Rangos de fechas arbitrarios.** La unidad es el mesociclo.

## Depende de

**Poder marcar una sesión como no esperada.** No existe todavía. Es una escritura
sobre el plan —una sesión que el entrenador declara que no correspondía— y por
eso no entra en una feature de sólo lectura. Es chica e independiente de la 002,
así que puede salir antes que el editor.

El panel funciona sin eso: muestra la adherencia cruda, que es la única que hay.
El criterio 9 existe para que la ausencia de marcas no deje una fila vacía
prometiendo una función que no está.

## Definiciones resueltas

| Pregunta | Decisión |
|---|---|
| ¿Cuándo cuenta que el atleta fue a entrenar? | Siempre. Toda serie prescrita cuenta, y no registrada es no hecha. Separar "no fue" de "fue y no registró" exigiría información que los datos no tienen. |

## Definiciones pendientes

`[NECESITA DEFINICIÓN]` **Si el atleta ve su propio panel, y cuánto.** El
volumen y la progresión son suyos. La adherencia es un juicio sobre él, y
mostrársela sin que el entrenador lo haya decidido cambia la relación entre los
dos. Es una decisión de producto, no de permisos.

## Cómo se relaciona con la constitución

- **Artículo I**: la analítica ya vive en `app/domain/` y no toca infraestructura.
  Esta feature no puede mover ese cálculo a una consulta SQL para acelerarlo sin
  pasar por una enmienda.
- **Artículo III**: el panel no agrega superficie de datos nueva; lee la que la
  001 ya aísla. El criterio 5 existe para que eso se verifique y no se asuma.
- **Artículo V**: queda una definición pendiente y **no habilita implementación**
  de la vista del atleta. El resto de la spec sí, incluidos los siete criterios de
  aceptación, que son todos del lado del entrenador.
- **Artículo IX**: se diseña contra los datos reales importados, no contra series
  inventadas. Los casos borde que importan —bloques sin registrar, un solo
  atleta, un patrón con 15 series en total— sólo aparecen ahí.

## Riesgos

**El panel puede quedar precioso y no responder nada.** El modo de falla de esta
feature no es un error, es una pantalla llena de gráficos correctos que no
contestan si el plan se está cumpliendo. La prueba es el criterio 2: si hay que
leer números para ver dónde está el problema, está mal.

**El hallazgo que motiva la feature es de una sola persona.** El 72% de isquios
es real y está medido, pero es un atleta. Que sea un patrón del producto y no una
particularidad suya es una hipótesis, no un dato, y esta spec no la necesita: el
panel tiene que contestar la pregunta, no tener razón sobre la respuesta.

**Los datos hoy son de una sola persona.** Todo lo que se vea bien con un atleta
y 17 semanas puede romperse con veinte atletas y dos años. La analítica se
calcula hoy en Python trayendo todas las series a memoria —deuda ya declarada—, y
esta feature es la primera que la va a ejercitar de verdad.

**Es la primera interfaz del proyecto.** No hay componentes, ni convenciones, ni
decisiones de tipografía o color tomadas. El plan tiene que decir qué de eso se
resuelve acá y qué se deja explícitamente abierto para la 004, que es mucho más
grande.
