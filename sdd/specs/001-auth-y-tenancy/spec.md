# 001 — Autenticación y aislamiento por tenant

Estado: borrador · Rama: `001-auth-y-tenancy`

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

## Qué tiene que pasar

### Alta de entrenador

Una persona se registra con email y queda con su espacio vacío. Al entrar por
primera vez no hay atletas, y la pantalla le ofrece crear el primero.

### Invitación de atleta

El entrenador crea un atleta cargando su nombre. El atleta existe en el sistema
aunque todavía no tenga cuenta: **el entrenador puede armarle el programa
completo antes de que el atleta se registre.** Esto no es un detalle — es como
trabajan hoy, arman la planilla y después la comparten.

El entrenador genera un link de invitación. Al aceptarlo, el atleta crea su
cuenta y queda asociado a su ficha existente, con todo el historial ya cargado.

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

## Fuera de alcance

- Roles dentro de un mismo entrenador (asistentes, gimnasios con varios coaches).
  Se contempla que exista más adelante, pero no se construye ahora.
- Login con Google o Apple. Sólo email.
- Autenticación de dos factores.
- Auditoría de accesos.
- Transferir un atleta de un entrenador a otro.
- Recuperación de contraseña propia: la resuelve el proveedor de auth.

## Definiciones pendientes

- `[NECESITA DEFINICIÓN]` ¿El link de invitación vence? Si vence, ¿en cuánto, y
  el entrenador puede regenerarlo?
- `[NECESITA DEFINICIÓN]` Un atleta que deja de entrenar con un coach, ¿qué pasa
  con su historial? ¿Lo conserva, lo pierde, se le exporta?
- `[NECESITA DEFINICIÓN]` ¿El mismo email puede ser entrenador y atleta a la vez?
  Pasa: entrenadores que también se entrenan. Si sí, el modelo de identidad
  cambia bastante.

Estas tres bloquean el `/plan`. Resolver con `/clarify` antes de seguir.

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
