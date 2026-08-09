# ADR 0005 — El cierre de sesión es del proveedor

Fecha: 2026-08-09 · Estado: aceptado

## Contexto

La tarea T-013 decía "cierre de sesión: el token anterior deja de servir", y al
implementarla apareció que la spec y la constitución se contradicen.

El **criterio de aceptación 8** de la spec 001 pide que, cerrada la sesión, el
token anterior deje de servir. El **artículo VIII** prohíbe escribir "manejo de
sesiones a mano". Y la propia constitución resuelve el empate: cuando una spec
choca contra un artículo, gana el artículo.

Cumplir el criterio 8 al pie de la letra exige que el backend lleve estado de
revocación —una lista de tokens anulados, o una marca por identidad— y consulte
ese estado en cada request. Eso es manejo de sesiones.

### Lo que hace Clerk, verificado

Los tokens de sesión de Clerk viven **60 segundos**. Al cerrar sesión se borra la
sesión, y a partir de ahí:

- no se emiten tokens nuevos;
- el último emitido sigue sirviendo hasta que vence, o sea a lo sumo 60 segundos.

La documentación de Clerk lo formula como garantía: el estado de autenticación
nunca queda inválido por más de 60 segundos.

O sea que delegar no deja la sesión abierta: la cierra con una ventana acotada y
conocida.

## Decisión

**El backend no lleva estado de sesión.** Cerrar sesión es una operación del
frontend contra Clerk. Nuestra parte es verificar `exp` en cada request, que ya
se hace, y no aceptar jamás un token vencido.

Se enmienda el criterio de aceptación 8 para que diga lo que realmente pasa:
cerrada la sesión el proveedor deja de emitir tokens, y el token en curso deja de
servir en cuanto vence, dentro de esa ventana. Una spec que promete inmediatez
que el sistema no da es peor que una que declara su límite — quien la lee cree
que está cubierto.

Va en la misma dirección que el ADR 0003, que ya había repartido las
responsabilidades: Clerk responde *quién sos*, y qué podés hacer lo resuelven
nuestra tabla de identidad y RLS. Las sesiones caen del lado de Clerk.

## Alternativa descartada

**Una columna `app_user.tokens_valid_from`.** Cerrar sesión la pone en el
instante actual, y se rechaza todo token con `iat` anterior. Cumple el criterio 8
literal, cierra la ventana de 60 segundos y además desloguea todos los
dispositivos a la vez.

No se descarta por costo: es una columna y una comparación, y se podría plegar en
la consulta de rol que el request ya hace. Se descarta porque es estado de sesión
nuestro, que es exactamente lo que el artículo VIII saca de la mesa, y porque el
beneficio es recortar una ventana de sesenta segundos en una aplicación donde lo
peor que alcanza un token robado en ese lapso es leer o escribir el entrenamiento
de una persona.

Si algún día la aplicación maneja algo donde sesenta segundos importen —cobros,
datos de salud regulados— esta decisión se revisa, y la conversación arranca por
enmendar el artículo VIII y no por saltearlo.

## Consecuencias

**A favor.** Cero estado de sesión en el backend: nada que expirar, nada que
limpiar, nada que se desincronice entre instancias. El artículo VIII se cumple
sin interpretaciones. Y la ventana no es una suposición nuestra sino una garantía
publicada del proveedor.

**En contra.** Hay una ventana de hasta 60 segundos en la que un token ya emitido
sigue sirviendo después del logout. Está documentada acá y en la spec, que es la
diferencia entre un límite conocido y una sorpresa.

Además, esto ata el criterio 8 a una característica de Clerk. Un proveedor con
tokens de una hora volvería la ventana inaceptable, así que el ADR 0003 gana una
condición nueva: cualquier reemplazo tiene que emitir tokens de vida corta.

**Lo que queda sin resolver.** No hay forma de que un entrenador cierre la sesión
de *otro* dispositivo desde el backend. La spec dice que la sesión se puede
cerrar "desde cualquier dispositivo", y con esta decisión eso significa que
podés desloguearte estés donde estés, no que puedas desloguear a los demás. Si lo
segundo hace falta, lo da Clerk desde su propio panel.

## Referencias

- [Session options — Clerk Docs](https://clerk.com/docs/guides/secure/session-options)
- [How We Roll, capítulo 8: Sessions](https://clerk.com/blog/how-we-roll-sessions)
- [Manual JWT verification — Clerk Docs](https://clerk.com/docs/guides/sessions/manual-jwt-verification)
