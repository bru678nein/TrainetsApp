# Prompt para pedirle el diseño de la interfaz a una IA

Copiá todo lo que está debajo de la línea. Está escrito para pegarse tal cual.

Dos notas para vos, no para la IA:

- Esto pide **diseño**, no código. Flujos, pantallas, estados y decisiones de
  interacción. La implementación es otra conversación y va después.
- **El editor de rutinas sí está incluido**, aunque el backend todavía no lo
  soporte. Es el 60% del esfuerzo de interfaz y el riesgo real del producto:
  conviene diseñarlo antes de construirlo, no después. Pero su presupuesto de
  interacción no se puede validar hasta que cronometres al entrenador en Excel
  — o sea la Fase 0, que sigue pendiente.

---

## Qué es

Una plataforma de coaching de fuerza. El entrenador arma la planificación de sus
atletas en mesociclos; el atleta registra lo que hizo desde el celular; el
entrenador ve si el plan se está cumpliendo y decide la semana siguiente.

Necesito que diseñes la interfaz. No escribas código: quiero flujos, pantallas,
estados y las decisiones de interacción justificadas.

## Contra qué compite de verdad

No compite contra otras apps de entrenamiento. **Compite contra Excel.**

Los usuarios son entrenadores de fuerza y powerlifting que hoy trabajan en
planillas de Google Sheets. Excel es gratis, y para el entrenador es rapidísimo:
copia y pega bloques, duplica una semana entera, arrastra para llenar. Lo que
Excel hace mal es el lado del atleta — abrir una planilla en el celular, en el
gimnasio, entre series, es horrible.

Ahí está la grieta, y ahí está la trampa: **si armar una semana en mi app cuesta
más que en la planilla, el entrenador vuelve a la planilla el primer día malo, y
va a tener razón.**

## Dos usuarios que no se parecen en nada

**El entrenador.** Escritorio, sentado, planificando. Hace trabajo en volumen: no
carga un ejercicio, carga doce. Repite estructuras entre semanas y entre atletas.
Viene de una herramienta donde el teclado alcanza para todo y el mouse es
opcional. Está acostumbrado a ver mucha información junta.

**El atleta.** Celular, parado en el gimnasio, con una mano, entre series, con
las manos sucias o con magnesio, a veces sin señal, con noventa segundos de
descanso. Abre la app, mira qué toca, hace la serie, anota, cierra. Ocho o diez
veces por sesión.

Son dos productos con la misma base de datos. Diseñarlos con el mismo criterio es
el error que quiero evitar.

## Lo que el modelo obliga a mostrar

Esto no es negociable porque sale de los datos reales, no de una preferencia:

- **La unidad es la serie, no el ejercicio.** La carga cambia entre series del
  mismo ejercicio: `30kg x6 / 25kg x7 / 20kg x10` es normal, no un caso raro. Un
  diseño que muestre "Sentadilla 3x8 80kg" pierde el dato.
- **Reps y RIR son rangos, no números.** "10 a 15 repeticiones", "RIR 2-3". La
  interfaz tiene que mostrar rangos y aceptar que el atleta cargue un valor
  dentro de ese rango.
- **La carga prescrita puede no existir.** Hay series autorreguladas: el
  entrenador sólo dice el RIR objetivo y el peso lo elige el atleta ese día. La
  pantalla del atleta tiene que funcionar igual de bien con y sin peso sugerido.
- **Prescripto y ejecutado son dos cosas distintas.** Lo que el entrenador planeó
  y lo que el atleta hizo se muestran juntos pero no se confunden. De esa
  diferencia sale la adherencia, que es la métrica que el entrenador mira para
  decidir la semana que viene.
- **La jerarquía es programa → mesociclo → semana → sesión → ejercicio → serie.**
  Son seis niveles. Navegarlos sin perderse es un problema de diseño real.

## Una persona puede ser las dos cosas

Muchos entrenadores se entrenan, y varios se entrenan con otro entrenador. Una
misma cuenta puede ser entrenadora de sus atletas y, al mismo tiempo, atleta de
otra persona.

El sistema **nunca adivina** desde qué rol estás mirando: es una elección
explícita. Necesito que el diseño resuelva dos cosas:

- que en todo momento se vea desde qué rol estás mirando, sin tener que
  deducirlo del contenido;
- que cambiar de rol sea barato y no se parezca a cerrar sesión.

Y algo que la interfaz tiene que dejar clarísimo: como entrenador ves tu espacio
de trabajo; como atleta ves tu programa. Son mundos separados aunque sean la
misma persona.

## Lo que quiero que diseñes

**El lado del atleta, que es lo que se usa todos los días**

1. La sesión de hoy: qué toca, en qué orden, con qué series.
2. Registrar una serie. Es la acción central del producto y la que más se
   repite.
3. Qué pasa con una serie que se saltea, o que se hace distinto de lo prescripto.
4. Ver lo ya hecho de la sesión sin perder de vista lo que falta.

**El lado del entrenador**

5. Entrar por primera vez, con el espacio vacío. Es la primera impresión y hoy no
   existe: quiero que el vacío enseñe qué hacer, no que se disculpe.
6. Sus atletas, y entrar a uno.
7. **El editor de rutinas.** Armar un mesociclo completo: semanas, sesiones,
   ejercicios, series prescritas. Acá es donde se gana o se pierde contra Excel.
   Diseñá pensando en **duplicar**: duplicar una semana sobre la siguiente,
   duplicar una sesión, duplicar un ejercicio ajustando la carga. Y pensá el
   teclado como camino principal, no como accesorio.
8. Ver si el plan se está cumpliendo: volumen semanal por patrón de movimiento,
   progresión de carga por ejercicio, adherencia por semana.

**Transversal**

9. Los estados vacíos, de carga y de error de cada pantalla. El vacío es el más
   importante de los tres.
10. Qué ve el atleta cuando no hay señal. En el gimnasio no hay, y una app de
    entrenamiento que necesita conexión no se usa. No hace falta que resuelvas la
    sincronización, sí que el diseño no la vuelva imposible.

## El requisito duro

Para cada tarea frecuente que diseñes, **declará cuánto cuesta**: cuántos toques
o cuántas teclas.

Dos que me importan más que el resto:

- Registrar una serie completa —repeticiones, peso, RIR— desde la pantalla del
  atleta.
- Armar una semana de entrenamiento desde cero, y duplicar una semana existente
  ajustando cargas.

Si no podés bajar el número, decímelo y explicá por qué. Prefiero un diseño
honesto sobre su costo que uno que promete fluidez y no la tiene.

## Qué NO diseñes

- Invitaciones, altas de atletas por link, o el ciclo de vida del vínculo entre
  entrenador y atleta. Es otra feature.
- Pantallas de administración, planes de pago o facturación.
- Onboarding con tour guiado. Si la interfaz necesita un tour, está mal.
- Nada de nutrición ni de rutinas generadas automáticamente. Este producto es
  profundidad en fuerza, no un generalista más.

## Cómo quiero la entrega

En este orden, y parando entre etapas para que yo opine:

1. **Los flujos primero**, en texto o diagrama. Qué hace cada usuario, en qué
   orden, y dónde se puede equivocar. Sin pantallas todavía.
2. **Wireframes de baja fidelidad** de las pantallas clave, con los estados
   —vacío, cargando, error, lleno— de cada una.
3. **Un sistema mínimo**: tipografía, escala de espaciado, colores con sus
   significados, y los tres o cuatro componentes que se repiten. Chico y
   consistente antes que completo.
4. **Alta fidelidad** sólo de las dos pantallas que más se usan: registrar una
   serie, y el editor de rutinas.

Para cada decisión que tomes, quiero el porqué en una línea. Y donde haya más de
una opción razonable, mostrame las dos y recomendá una en vez de elegir en
silencio.

## Tono y detalles

- Todo en **castellano rioplatense**, natural, sin solemnidad y sin traducciones
  literales del inglés.
- Vocabulario del ambiente: mesociclo, RIR, series, repeticiones, patrón de
  movimiento, tonelaje. Los usuarios lo usan; no lo simplifiques.
- Mobile-first para el atleta, escritorio para el entrenador. No es la misma
  interfaz achicada.
- Accesible de verdad: contraste que sirva en un gimnasio con luz mala, y áreas
  de toque grandes para una mano con magnesio.

## Antes de empezar

Si algo de este brief te parece equivocado, o si ves un supuesto que no me
conviene, decilo antes de diseñar. Y si te falta información para decidir algo
importante, preguntá en vez de asumir.
