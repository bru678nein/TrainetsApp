# 003 — Invitaciones y ciclo de vida del vínculo

Estado: clarificada, lista para `/plan` · Rama: `003-invitaciones-y-vinculos`

Depende de la 001, que define la identidad y el aislamiento. Esta feature es la
que hace que el atleta pueda entrar por su cuenta y que la relación con un
entrenador tenga principio y fin.

---

## Por qué

Hoy el atleta no entra a la app: usa el HTML autocontenido que genera
`backend/scripts/gen_app.py`. Sirve como puente y hay que sostenerlo hasta acá,
pero no tiene cuenta, no tiene historial y el entrenador no ve lo que cargó
salvo que le manden el CSV.

Y del otro lado, hoy no hay forma de terminar una relación. Un atleta que deja
de entrenar queda `is_active = false` y su historial queda colgando de un
entrenador para siempre, sin que ninguno de los dos sepa qué pasa con él.

## Para quién

- **Entrenador**: le pasa un link al atleta y a partir de ahí el atleta carga
  sus propias series. Cuando la relación termina, la cierra sin perder su
  trabajo.
- **Atleta**: entra con su cuenta y encuentra el programa que su entrenador ya
  le había armado, con todo el historial cargado.

## Qué tiene que pasar

### Invitación

El entrenador genera un link de invitación para una ficha de atleta que ya
existe —creada en la 001, con el programa completo si quiso armarlo antes.

Al aceptarlo, el atleta crea su cuenta, o usa la que ya tiene si ya está en el
sistema, y queda asociado a esa ficha con todo lo que había cargado.

El link **vence a los siete días**. El entrenador puede generar uno nuevo cuando
quiera, y hacerlo invalida el anterior. Un link no es una credencial que se
mande con cuidado: viaja por WhatsApp, queda en el historial de un chat y a
veces en un grupo. Sin vencimiento, es acceso permanente a la ficha de un atleta
para cualquiera que lo tenga.

Un link vencido dice que venció y le indica al atleta que le pida otro. No cae
en el mismo error genérico que un link inventado: acá la distinción ayuda a la
persona correcta y no le sirve de nada a un atacante, porque el link vencido ya
no vale.

El link es nuestro, no del proveedor de auth. La ficha del atleta existe antes
que la cuenta, y las invitaciones del proveedor obligan al orden inverso. Ver
ADR 0003.

### Pausar no es archivar

Son dos estados distintos y la diferencia es quién puede escribir.

**Pausado** es lo que hoy hace `is_active = false`: el atleta desaparece del
listado y nada más. El entrenador lo sigue editando. Existe para el caso más
común de todos —alguien se lesiona, o para tres meses— donde el entrenador
justamente necesita prepararle el programa de vuelta antes de que vuelva.

**Archivado** es el fin del vínculo, y es el que define el resto de esta sección.

Tenerlos separados es la diferencia entre esconder a alguien de una lista y
declarar que la relación terminó. Colapsarlos le sacaría al entrenador una
capacidad que hoy tiene: desactivar a un atleta en pausa y no poder tocarle el
programa hasta reactivarlo.

### Fin del vínculo

Cuando el entrenador da de baja a un atleta, el vínculo se archiva. **No se borra
nada.**

Lo archiva el entrenador, siempre. Que el atleta se vaya por su cuenta es una
relación que terminó en la vida real, pero no una acción del atleta en la app:
está fuera de alcance más abajo, y por eso acá no aparece como disparador.

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
frecuente —la gente cambia de entrenador— y es el que obligó a que el modelo de
la 001 admita varios vínculos por persona.

El entrenador nuevo no ve nada de los anteriores. Que la persona sea la misma no
conecta los dos espacios.

## Criterios de aceptación

1. Un entrenador crea un atleta, le arma un programa completo y recién después
   lo invita; al aceptar, el atleta ve todo el historial.
2. Un link de invitación aceptado a los seis días asocia la cuenta. A los ocho,
   es rechazado con un motivo distinguible de "link inválido".
3. Generado un link nuevo, el anterior deja de servir.
4. Un link ya usado no sirve una segunda vez.
5. Sobre un vínculo archivado, entrenador y atleta leen el historial completo, y
   todo intento de prescribir o de registrar una serie es rechazado.
6. Reactivado el vínculo, el historial previo sigue visible y se puede volver a
   prescribir sobre él.
7. **El caso frecuente: cambio de entrenador.** Un atleta con el vínculo
   archivado con el entrenador A acepta la invitación del entrenador B usando la
   misma cuenta. Ve su programa nuevo, y sigue viendo en solo lectura el
   historial con A. B no obtiene nada de lo de A: ni el historial, ni que exista
   A, ni que la persona haya entrenado antes con alguien.
8. La misma persona acumula vínculos archivados con tres entrenadores distintos
   y uno activo con un cuarto. Ninguno de los cuatro ve a los otros tres.
9. **Pausado no bloquea la escritura.** El entrenador pausa a un atleta, le
   modifica el programa, y el cambio se guarda. Es lo que separa pausar de
   archivar, y si este criterio pasa contra una implementación que los trata
   igual, el criterio está mal escrito.
10. Un atleta pausado no aparece en el listado del entrenador, y aparece de nuevo
    al reanudarlo.
11. Una invitación pendiente sobre una ficha que se archiva deja de servir. Sobre
    una ficha que se pausa, sigue sirviendo.
12. El entrenador invita a una persona que ya es atleta suyo y la invitación es
    rechazada con un motivo propio, distinguible de un link vencido y de uno
    inválido.

## Fuera de alcance

- Transferir un atleta de un entrenador a otro conservando el vínculo original.
  Que una persona entrene con dos entrenadores sí está en alcance; mover una
  ficha de un espacio a otro, no.
- Exportar el historial. El archivado lo deja legible, que es lo que resuelve el
  problema hoy.
- Notificar al atleta por email que lo invitaron. El entrenador manda el link
  por donde ya se habla con él.
- Que el atleta se dé de baja solo. La baja la hace el entrenador; el flujo del
  atleta que se va por su cuenta se define cuando haya alguien que lo pida.

## Definiciones resueltas

| Pregunta | Decisión |
|---|---|
| ¿El link de invitación vence? | Sí, a los 7 días. Regenerable, y regenerar invalida el anterior. |
| ¿Qué pasa con el historial cuando termina el vínculo? | Se archiva. Ambos leen, ninguno edita. No se borra ni se transfiere. |
| ¿Dar de baja y archivar son lo mismo? | No. **Pausado** esconde del listado y el entrenador sigue escribiendo; **archivado** cierra el vínculo y nadie escribe. Lo que hoy hace `is_active` es pausar. |
| ¿Qué pasa si alguien acepta una invitación a un entrenador del que ya es atleta? | Se rechaza con un motivo propio. El índice `athlete_coach_user_uq` lo impide en la base de todos modos, y un error de unicidad no le explica nada a quien está del otro lado. Pasa cuando el entrenador crea la ficha dos veces. |
| ¿Sobrevive una invitación pendiente al cambio de estado? | Archivar la invalida —el vínculo terminó—. Pausar no, porque la ficha sigue viva. |

## Cómo se relaciona con la constitución

- Artículo III: el archivado agrega un segundo eje al aislamiento — no alcanza
  con filtrar por entrenador, hay que impedir la escritura sobre lo archivado.
- Artículo V: las cuatro exclusiones de arriba son parte del alcance, no cortesía.
- Artículo VIII: la invitación es lógica propia, no del proveedor de auth. No
  contradice el artículo, que prohíbe manejar credenciales y sesiones.

## Riesgos

El aislamiento pasa a tener dos ejes: por entrenador y por estado del vínculo.
Un vínculo archivado es legible pero no escribible, y esa es una condición que
los tests del artículo III no cubren tal como está redactado —habla de que el
coach B no vea lo de A, no de que nadie escriba sobre lo cerrado. El plan tiene
que decir cómo se verifica que ningún endpoint de escritura la ignore, con el
mismo criterio que el test que recorre todas las rutas en la 001.

Si esa verificación queda como un `if` por endpoint, se rompe igual que se
rompería el aislamiento por tenant: alguien agrega una ruta y se olvida.

El segundo es el token de invitación. Es una credencial de un solo uso que da
acceso a datos personales de un atleta, y lo estamos escribiendo nosotros. Tiene
que ser imposible de adivinar, de un solo uso, y su comparación no puede filtrar
información por tiempo de respuesta.
