# 001 — Autenticación y aislamiento por tenant

Estado: listo para `/plan` · Rama: `001-auth-y-tenancy`

Sirve como referencia de formato para las specs siguientes.

---

## Por qué

Hoy cualquiera que conozca el UUID de un atleta puede leer sus datos: los
endpoints no filtran por entrenador. Mientras haya un solo entrenador en la base
no se nota, y en el momento en que entre el segundo es una filtración.

Es además lo primero que mira un revisor técnico al abrir el repo.

## Para quién

- **Entrenador**: entra con su cuenta y ve únicamente sus atletas.
- **Atleta**: entra con su cuenta, ve su programa y registra sus series. No ve
  nada de otros atletas, ni siquiera de los del mismo entrenador.

Entrenador y atleta son **roles, no personas**. La misma persona puede tener los
dos, y eso condiciona todo lo que sigue.

## Qué tiene que pasar

### Una persona, varios roles

Una persona es una sola cuenta. Sobre esa cuenta puede ser entrenador de sus
atletas y, a la vez, atleta de uno o más entrenadores.

No es un caso de borde: los entrenadores entrenan, y muchos se entrenan con otro
entrenador. Que el sistema los obligue a tener dos cuentas con dos emails es la
clase de fricción que hace que prueben la app una vez y no vuelvan.

Lo que se exige:

- La persona entra una sola vez. Si tiene más de un rol, elige desde dónde está
  mirando, y cambiar de rol no la obliga a loguearse de nuevo.
- Un entrenador puede crearse una ficha de atleta en su propio espacio y
  prescribirse un programa como a cualquier otro.
- Una persona puede ser atleta de dos entrenadores al mismo tiempo. Cada
  entrenador ve únicamente el programa que él prescribió; ninguno se entera del
  otro.
- Ser atleta de alguien no da ninguna visibilidad sobre el espacio de ese
  alguien más allá del propio programa. Un entrenador que es cliente de otro
  entrenador sigue sin ver los atletas del otro.

### Alta de entrenador

Una persona se registra con email y queda con su espacio vacío. Al entrar por
primera vez no hay atletas, y la pantalla le ofrece crear el primero.

### Invitación de atleta

El entrenador crea un atleta cargando su nombre. El atleta existe en el sistema
aunque todavía no tenga cuenta: **el entrenador puede armarle el programa
completo antes de que el atleta se registre.** Esto no es un detalle — es como
trabajan hoy, arman la planilla y después la comparten.

El entrenador genera un link de invitación. Al aceptarlo, el atleta crea su
cuenta —o usa la que ya tiene, si ya está en el sistema— y queda asociado a su
ficha existente, con todo el historial ya cargado.

El link **vence a los siete días**. El entrenador puede generar uno nuevo cuando
quiera, y hacerlo invalida el anterior. Un link no es una credencial que se
mande con cuidado: viaja por WhatsApp, queda en el historial de un chat y a
veces en un grupo. Sin vencimiento, es acceso permanente a la ficha de un atleta
para cualquiera que lo tenga.

Un link vencido dice que venció y le indica al atleta que le pida otro. No cae
en el mismo error genérico que un link inventado: acá la distinción ayuda a la
persona correcta y no le sirve de nada a un atacante, porque el link vencido ya
no vale.

### Fin del vínculo

Cuando el entrenador da de baja a un atleta, o el atleta deja de entrenar con
él, el vínculo se archiva. **No se borra nada.**

Archivado: los dos siguen leyendo el historial completo, y ninguno de los dos
puede modificarlo. No se prescriben sesiones nuevas ni se registran series sobre
un vínculo archivado. Si la persona vuelve con ese mismo entrenador, el vínculo
se reactiva y el historial sigue donde estaba.

El motivo de no elegir un dueño: ese historial es, al mismo tiempo, el trabajo
del entrenador y el progreso del atleta. Cualquier respuesta sobre de quién es
requiere una definición de producto que hoy no tenemos, y borrarlo es la única
opción irreversible de todas.

**Archivar un vínculo no cierra la cuenta.** La misma persona puede empezar con
otro entrenador y conserva, en solo lectura, todo lo anterior. Este es el caso
frecuente —la gente cambia de entrenador— y es el que obliga a que una persona
pueda estar vinculada a varios entrenadores: no hace falta que entrene con dos a
la vez para necesitarlo, alcanza con que haya entrenado con uno antes.

El entrenador nuevo no ve nada de los anteriores. Que la persona sea la misma no
conecta los dos espacios.

### Aislamiento

Un entrenador nunca obtiene datos de atletas de otro entrenador, por ninguna vía:
ni listados, ni acceso directo por identificador, ni mensajes de error que
delaten existencia. Un identificador ajeno responde igual que uno inexistente.

Un atleta sólo accede a sus propios datos, y sólo puede registrar series que le
fueron prescritas a él.

### Sesión

La sesión sobrevive al cierre del navegador: el atleta no debería tener que
loguearse cada vez que entra al gimnasio. La sesión se puede cerrar
explícitamente desde cualquier dispositivo.

## Criterios de aceptación

Se escriben como pruebas. Si alguno no se puede automatizar, la spec está
incompleta.

1. Dados dos entrenadores con un atleta cada uno, el listado de atletas de A
   contiene sólo el suyo.
2. Dado el identificador del atleta de B, A recibe la misma respuesta que ante un
   identificador inexistente. La respuesta no distingue "no existe" de "no es
   tuyo".
3. Esto vale para **todos** los endpoints que devuelven datos, no sólo el
   listado. La prueba recorre el listado de rutas y falla si alguna no está
   cubierta.
4. Un atleta que intenta registrar una serie prescrita a otro atleta es rechazado.
5. Un entrenador puede crear un atleta, armarle un programa completo y recién
   después invitarlo; al aceptar, el atleta ve todo el historial.
6. Una petición sin credenciales a cualquier endpoint de datos es rechazada.
7. Una petición con un token vencido es rechazada, y el mensaje distingue
   "vencido" de "inválido" para que el cliente sepa si conviene renovar.
8. Cerrada la sesión, el token anterior deja de servir.
9. Una cuenta de entrenador se crea una ficha de atleta en su propio espacio y
   se prescribe un programa. Lo ve como entrenador y lo registra como atleta,
   sin salir de la sesión.
10. Una misma cuenta es atleta de dos entrenadores distintos. Cada uno ve sólo
    el programa que prescribió, y el listado de atletas de cada uno no revela
    nada del otro.
11. Un entrenador que además es atleta de otro no obtiene, por esa vía, ningún
    dato del espacio del otro fuera de su propio programa.
12. Un link de invitación aceptado a los seis días asocia la cuenta. A los ocho,
    es rechazado con un motivo distinguible de "link inválido".
13. Generado un link nuevo, el anterior deja de servir.
14. Sobre un vínculo archivado, entrenador y atleta leen el historial completo, y
    todo intento de prescribir o de registrar una serie es rechazado.
15. Reactivado el vínculo, el historial previo sigue visible y se puede volver a
    prescribir sobre él.
16. **El caso frecuente: cambio de entrenador.** Un atleta con el vínculo
    archivado con el entrenador A acepta la invitación del entrenador B usando
    la misma cuenta. Ve su programa nuevo, y sigue viendo en solo lectura el
    historial con A. B no obtiene nada de lo de A: ni el historial, ni que exista
    A, ni que la persona haya entrenado antes con alguien.
17. La misma persona acumula vínculos archivados con tres entrenadores distintos
    y uno activo con un cuarto. Ninguno de los cuatro ve a los otros tres.

## Fuera de alcance

- Roles dentro de un mismo entrenador (asistentes, gimnasios con varios coaches).
  Se contempla que exista más adelante, pero no se construye ahora.
- Más de un espacio de entrenador por persona. Una cuenta tiene a lo sumo un
  perfil de entrenador; lo que puede tener varios es el rol de atleta.
- Login con Google o Apple. Sólo email.
- Autenticación de dos factores.
- Auditoría de accesos.
- Transferir un atleta de un entrenador a otro conservando el vínculo original.
  Que una persona entrene con dos entrenadores sí está en alcance; mover una
  ficha de un espacio a otro, no.
- Exportar el historial. El archivado lo deja legible, que es lo que resuelve el
  problema hoy.
- Recuperación de contraseña propia: la resuelve el proveedor de auth.

## Definiciones resueltas

Las tres que bloqueaban el `/plan`, con la decisión tomada:

| Pregunta | Decisión |
|---|---|
| ¿El link de invitación vence? | Sí, a los 7 días. Regenerable, y regenerar invalida el anterior. |
| ¿Qué pasa con el historial cuando termina el vínculo? | Se archiva. Ambos leen, ninguno edita. No se borra ni se transfiere. |
| ¿La misma persona puede ser entrenador y atleta? | Sí, y además atleta de varios entrenadores. |

La tercera es la que más arrastra: obliga a que identidad y rol sean cosas
distintas en el modelo, en vez de que cada rol traiga su propia identidad
pegada. Cómo se representa eso es decisión del `plan.md`.

Vale registrar cómo se llegó, porque el razonamiento intuitivo lleva al lugar
equivocado. La discusión arrancó por el entrenador que también se entrena, que
parece un caso raro y tienta a dejarlo afuera para ahorrar trabajo. **Dejarlo
afuera no ahorra nada.** Lo que fuerza el cambio no es ese caso sino el archivado
que se decidió dos filas más arriba: si el vínculo con el entrenador anterior se
conserva, la persona que cambia de entrenador necesita un vínculo nuevo sin
perder el viejo. Eso es rotación normal, le pasa a cualquier atleta, y ya
requiere que una identidad admita varios vínculos.

O sea que el multi-vínculo entra por la puerta del caso más común, no del más
exótico. Una spec que sólo hubiera mirado el caso exótico habría concluido que
convenía prohibirlo, y habría entregado una app donde nadie puede cambiar de
entrenador.

## Cómo se relaciona con la constitución

- Artículo III (aislamiento por tenant) es el motivo de existir de esta spec.
- Artículo VIII (nada de auth propia): el proveedor se elige en el plan.
- Artículo IV: la lógica de resolución de tenant vive en el dominio y se testea
  antes de implementarse.

## Riesgos

El mayor es dejar la verificación de tenant en manos de cada endpoint: alcanza
con que alguien se olvide en uno para abrir el agujero. El plan tiene que
resolverlo de forma que **el default sea seguro** y olvidarse rompa
ruidosamente, no silenciosamente. La combinación de RLS en la base con una
dependencia obligatoria en la capa HTTP es el camino esperado, pero la decisión
va en `plan.md`.

El segundo aparece con los roles múltiples: si el tenant se resuelve a partir de
la identidad, una persona con dos roles tiene dos respuestas válidas y el
sistema tiene que saber cuál corresponde a cada request. Resolverlo mal en la
dirección permisiva —quedarse con el rol más amplio ante la duda— convierte a
cualquier atleta que además sea entrenador en una vía de escape del aislamiento.
El plan tiene que definir de dónde sale el rol activo y qué pasa cuando no viene.

Lo que **no** es un riesgo, aunque lo parezca: que un atleta tenga varios
vínculos no complica el aislamiento. El entrenador lee por su espacio y el
atleta por su identidad; son dos predicados independientes sobre las mismas
tablas, y una persona con cuatro vínculos simplemente matchea cuatro filas. La
dificultad de los vínculos múltiples es de interfaz —qué programa estoy mirando,
cómo cambio de uno a otro— y esa discusión pertenece a las features 002 y 003,
no acá.

El tercero es que el aislamiento ahora tiene dos ejes, no uno: por entrenador y
por vínculo archivado. Un vínculo archivado es legible pero no escribible, y esa
es una condición que los tests del artículo III no cubren tal como está escrito
hoy. El plan tiene que decir cómo se verifica que ningún endpoint de escritura
la ignore.
