# 001 — Identidad y aislamiento por tenant

Estado: listo para `/plan` · Rama: `001-identidad-y-aislamiento`

Sirve como referencia de formato para las specs siguientes.

Esta feature nació partida en dos. La invitación de atletas y el ciclo de vida
del vínculo entrenador–atleta viven en la 003; acá está lo que cierra el agujero
de seguridad y define quién es quién. La razón de la partición está al final.

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
- Una persona puede estar vinculada a varios entrenadores. Cada entrenador ve
  únicamente lo que él prescribió; ninguno se entera del otro.
- Ser atleta de alguien no da ninguna visibilidad sobre el espacio de ese
  alguien más allá del propio programa. Un entrenador que es cliente de otro
  entrenador sigue sin ver los atletas del otro.

**El modelo tiene que admitir varios vínculos por persona desde el día uno**,
aunque el flujo que los crea llegue con la 003. El motivo está en las
definiciones resueltas: no es el entrenador que se entrena solo lo que lo fuerza,
es que la gente cambia de entrenador.

### Alta de entrenador

Una persona se registra con email y queda con su espacio vacío. Al entrar por
primera vez no hay atletas, y la pantalla le ofrece crear el primero.

El entrenador crea un atleta cargando su nombre. El atleta existe en el sistema
aunque todavía no tenga cuenta: **el entrenador puede armarle el programa
completo antes de que el atleta se registre.** Esto no es un detalle — es como
trabajan hoy, arman la planilla y después la comparten. Cómo hace el atleta para
reclamar esa ficha es la feature 003.

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

Cerrarla es una operación contra el proveedor de identidad, no contra esta API:
el backend no guarda sesiones (artículo VIII). "Desde cualquier dispositivo"
significa que podés desloguearte estés donde estés, no que puedas cerrar la
sesión de otro. Ver el ADR 0005.

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
5. Una petición sin credenciales a cualquier endpoint de datos es rechazada.
6. Una petición con un token vencido es rechazada, y el mensaje distingue
   "vencido" de "inválido" para que el cliente sepa si conviene renovar.
7. Un token emitido para otro origen es rechazado.
8. Cerrada la sesión, el proveedor deja de emitir tokens para esa persona, y
   el que estaba en curso deja de servir en cuanto vence — a lo sumo 60
   segundos después. **Enmendado**: la versión anterior prometía que dejaba de
   servir en el acto, y eso exige que el backend lleve estado de revocación, que
   es lo que prohíbe el artículo VIII. La constitución resuelve el empate a
   favor del artículo. El razonamiento y la alternativa descartada están en el
   ADR 0005.
9. Una cuenta de entrenador se crea una ficha de atleta en su propio espacio y
   se prescribe un programa. Lo ve como entrenador y lo registra como atleta,
   sin salir de la sesión.
10. Una misma cuenta está vinculada a dos entrenadores distintos. Cada uno ve
    sólo lo que prescribió, y el listado de atletas de cada uno no revela nada
    del otro.
11. Un entrenador que además es atleta de otro no obtiene, por esa vía, ningún
    dato del espacio del otro fuera de su propio programa.

## Fuera de alcance

- **Invitación de atletas y ciclo de vida del vínculo.** Generar el link, que
  venza, aceptarlo, archivar la relación y reactivarla: todo eso es la feature
  003. Acá se construye el modelo que lo admite, no el flujo.
- Roles dentro de un mismo entrenador (asistentes, gimnasios con varios coaches).
  Se contempla que exista más adelante, pero no se construye ahora.
- Más de un espacio de entrenador por persona. Una cuenta tiene a lo sumo un
  perfil de entrenador; lo que puede tener varios es el vínculo como atleta.
- Login con Google o Apple. Sólo email.
- Autenticación de dos factores.
- Auditoría de accesos.
- Recuperación de contraseña propia: la resuelve el proveedor de auth.

## Definiciones resueltas

La pregunta que bloqueaba esta feature era si la misma persona puede ser
entrenador y atleta. **Sí, y además puede estar vinculada a varios entrenadores.**

Vale registrar cómo se llegó, porque el razonamiento intuitivo lleva al lugar
equivocado. La discusión arrancó por el entrenador que también se entrena, que
parece un caso raro y tienta a dejarlo afuera para ahorrar trabajo. **Dejarlo
afuera no ahorra nada.** Lo que fuerza el cambio es la decisión de la feature
003 de archivar el vínculo en vez de borrarlo: si la relación con el entrenador
anterior se conserva, la persona que cambia de entrenador necesita un vínculo
nuevo sin perder el viejo. Eso es rotación normal, le pasa a cualquier atleta.

O sea que el multi-vínculo entra por la puerta del caso más común, no del más
exótico. Una spec que sólo hubiera mirado el caso exótico habría concluido que
convenía prohibirlo, y habría entregado una app donde nadie puede cambiar de
entrenador.

Consecuencia para el modelo: identidad y rol tienen que ser cosas distintas, en
vez de que cada rol traiga su propia identidad pegada. Cómo se representa es
decisión del `plan.md`.

## Por qué esta feature se partió

La versión original cubría también las invitaciones y el archivado. El plan daba
bastante más de veinte tareas, que según `sdd/README.md` es la señal de que era
más de una feature.

El corte se hizo por urgencia, no por tamaño: esta mitad cierra el agujero de
seguridad y no depende de nada. La otra es funcionalidad de producto y recién
hace falta cuando el atleta tenga que entrar por su cuenta — hasta entonces lo
cubre `backend/scripts/gen_app.py`, que es lo que usa hoy.

## Cómo se relaciona con la constitución

- Artículo III (aislamiento por tenant) es el motivo de existir de esta spec.
- Artículo VIII (nada de auth propia): el proveedor está decidido en el ADR 0003.
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

Lo que **no** es un riesgo, aunque lo parezca: que una persona tenga varios
vínculos no complica el aislamiento. El entrenador lee por su espacio y el
atleta por su identidad; son dos predicados independientes sobre las mismas
tablas, y una persona con cuatro vínculos simplemente matchea cuatro filas. La
dificultad de los vínculos múltiples es de interfaz —qué programa estoy mirando,
cómo cambio de uno a otro— y esa discusión pertenece a las features 002 y 004.

El tercero es de migración: la base ya tiene datos reales importados de la
planilla. El plan tiene que decir cómo se pobla la identidad de las filas que ya
existen sin perderlas, y la migración tiene que revertir limpio — CI corre
`upgrade head` seguido de `downgrade base`.
