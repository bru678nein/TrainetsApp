# Plan — 003 Invitaciones y ciclo de vida del vínculo

Cómo se construye lo que la spec pide. La spec dice qué y por qué; acá aparecen
tablas, funciones y policies.

Se apoya entero en la 001: identidad, rol activo y aislamiento por tenant ya
existen y no se tocan. Esta feature agrega un **segundo eje** al aislamiento —el
estado del vínculo— y la mayor parte del riesgo está ahí, no en las invitaciones.

---

## 1. Los dos estados del vínculo

Hoy `athlete.is_active` es un booleano que hace una sola cosa: filtrar el listado
del entrenador (`app/api/routes.py`, el único lugar donde se lee). No bloquea
nada.

La spec pide tres situaciones distintas, así que la columna pasa a ser un estado:

| Estado | Aparece en el listado | El entrenador escribe | El atleta escribe |
|---|---|---|---|
| `activo` | sí | sí | sí |
| `pausado` | no | **sí** | sí |
| `archivado` | no | no | no |

`pausado` existe para el atleta que para tres meses y vuelve, que es el caso que
obliga a que escribir siga permitido: el entrenador le prepara el programa de
vuelta *antes* de que vuelva. Colapsar los dos estados le sacaría esa capacidad,
y hoy la tiene.

### Migración

`athlete.estado text NOT NULL` con `CHECK (estado IN ('activo','pausado','archivado'))`.
Texto con `CHECK` y no un `ENUM` de Postgres: a un enum **no se le puede sacar un
valor**, así que la migración que agregue un estado no tiene `downgrade` posible.
Y este proyecto ya tiene un estado más asomando —el atleta que se va por su
cuenta, hoy fuera de alcance—. Con un `CHECK`, agregar y sacar valores son las
dos un `ALTER TABLE`.

El backfill es la decisión importante de toda la migración:

```
is_active = true   ->  'activo'
is_active = false  ->  'pausado'
```

**Nunca a `archivado`.** Lo que `is_active = false` significa hoy es "escondido
de la lista, y el entrenador lo sigue editando", que es exactamente `pausado`.
Mapearlo a `archivado` cerraría vínculos que nadie decidió cerrar y dejaría
programas de solo lectura sin que ningún humano lo haya pedido. Es irreversible
en la práctica aunque el `downgrade` exista, porque la información de cuáles
estaban en pausa ya no se puede reconstruir.

El índice parcial `athlete_coach_idx` está definido `WHERE is_active` y se
reconstruye como `WHERE estado = 'activo'`. `is_active` se borra en la misma
migración: dejar las dos es garantizar que se desincronicen.

## 2. La invitación

Tabla nueva:

```
invitation
  id           uuid pk
  athlete_id   uuid fk -> athlete (on delete cascade)
  token_hash   bytea not null          -- sha256 del token, nunca el token
  created_at   timestamptz not null
  expires_at   timestamptz not null    -- guardado, no calculado al leer
  accepted_at  timestamptz null
  accepted_by  uuid fk -> app_user null
  revoked_at   timestamptz null
```

**Se guarda el hash, no el token.** Una filtración de la base no entrega links
vivos. El token se genera con `secrets.token_urlsafe(32)`, se muestra una vez y
no se puede volver a ver.

**Eso también resuelve el riesgo de timing que declara la spec**, y conviene
decir cómo, porque no es por usar una comparación en tiempo constante: es que no
hay ninguna comparación. Se hashea lo que llega y se busca por índice. No existe
un `==` contra el secreto cuyo tiempo dependa de cuántos caracteres coincidían.

**`expires_at` se guarda, no se calcula.** Si fuera `created_at + interval '7
days'` evaluado al leer, cambiar la constante mañana extendería o mataría links
que ya están en manos de gente. Guardado, el link vale lo que valía cuando se
emitió.

**Una sola invitación usable por ficha**, con un índice parcial:

```sql
CREATE UNIQUE INDEX invitation_pendiente_uq ON invitation (athlete_id)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;
```

El predicado no menciona `expires_at` a propósito: `now()` no es inmutable y
Postgres no lo acepta en un índice. La consecuencia es buena igual — generar un
link nuevo **obliga** a revocar el anterior en la misma transacción, porque si no
el índice lo rechaza. El criterio 3 de la spec queda garantizado por el esquema y
no por que alguien se acuerde de hacerlo.

## 3. Aceptar una invitación cruza el límite del tenant

Es la operación rara de esta feature y merece su propia sección.

Quien acepta tiene identidad —viene con un token del proveedor— pero **no tiene
ningún vínculo con la ficha que va a aceptar**. No existe todavía. Así que no hay
contexto de tenant que setear, y ninguna policy de la 001 lo dejaría escribir.

La forma ya existe en el repositorio: es la misma del alta de entrenador, con
`require_identity_for_signup` y `signup_session` en `app/api/deps.py`. El
endpoint de aceptación cuelga de ahí, no del router de datos.

Pero la identidad sola no alcanza, porque RLS sigue aplicando. La escritura la
hace una función:

```
app_aceptar_invitacion(p_token_hash bytea, p_user_id uuid) -> text
```

`SECURITY DEFINER`, con `search_path` fijado y `EXECUTE` revocado de `PUBLIC`,
igual que los helpers de la 0004. Adentro hace todo y en orden: busca por hash,
verifica que no esté revocada, ni usada, ni vencida, comprueba que la ficha no
tenga ya otra cuenta y que esa persona no sea ya atleta de ese entrenador, asocia
y marca la invitación como usada.

**Recibe un `app_user.id` ya resuelto y no el `sub`**, que es la corrección que
apareció al implementarlo. Crear la identidad necesita el email y el nombre, que
viajan en el token y se leen en Python — es el mismo corte que ya usa el alta de
entrenador. Esta función hace lo que tiene que ser atómico y nada más.

Devuelve **cuál** de esos casos ocurrió, no un booleano: `aceptada`, `vencida`,
`inexistente`, `usada`, `ya_vinculado`. La spec pide distinguir vencida de
inválida, y el criterio 12 pide un motivo propio para la persona que ya está
vinculada.

Que sea una sola función es la parte que importa. La alternativa —un endpoint con
una sesión sin RLS— reparte el permiso de cruzar el límite por el código, y el
día que alguien agregue una consulta al lado, la hace con el mismo privilegio sin
notarlo. Acá hay exactamente un lugar auditable, y su cuerpo es la lista de
verificaciones.

## 4. Cómo se bloquea la escritura sobre lo archivado

El riesgo que la spec declara: si esto termina siendo un `if` por endpoint, se
rompe igual que se rompería el aislamiento por tenant.

### Por qué no alcanza con lo que ya hay

Las 18 policies de la 0004 son todas `FOR ALL`, con `USING` y `WITH CHECK`. En
una policy `FOR ALL`, `USING` sirve a `SELECT`, `UPDATE` y `DELETE`, y
`WITH CHECK` a `INSERT` y `UPDATE`.

Lo archivado tiene que **leerse** y no **borrarse**. Las dos cosas pasan por
`USING`. Con `FOR ALL` no se puede expresar.

Y agregar la condición sólo a `WITH CHECK` deja un agujero. Medido, no supuesto
(`spike/restrictive.py`):

```
1. FOR ALL con WITH CHECK
  SELECT sobre archivada             1 fila(s)
  UPDATE sobre archivada             RECHAZADO
  DELETE sobre archivada             1 fila(s)     <- borra
```

Es el espejo exacto de la lección de la 001, donde `USING` no cubría `INSERT`. Un
entrenador no podría editar una serie de un vínculo archivado, pero podría
borrarla, y todos los tests de lectura quedarían verdes.

### La forma que sí

Las 18 policies existentes **no se tocan**, y encima van policies `RESTRICTIVE`,
que Postgres combina con `AND` en vez de con `OR`:

```sql
CREATE POLICY <tabla>_vinculo_vivo_insert ON <tabla>
    AS RESTRICTIVE FOR INSERT WITH CHECK (app_vinculo_escribible_<tabla>(<tabla>.<fk>));
CREATE POLICY <tabla>_vinculo_vivo_update ON <tabla>
    AS RESTRICTIVE FOR UPDATE USING (...) WITH CHECK (...);
CREATE POLICY <tabla>_vinculo_vivo_delete ON <tabla>
    AS RESTRICTIVE FOR DELETE USING (...);
```

Medido:

```
2. Permisiva + RESTRICTIVE por comando
  SELECT sobre archivada             1 fila(s)     <- sigue legible
  UPDATE sobre archivada             0 fila(s)
  DELETE sobre archivada             0 fila(s)
  INSERT de fila archivada           RECHAZADO
  DELETE sobre la viva               1 fila(s)     <- control
  UPDATE sobre la viva               1 fila(s)     <- control
```

Tres ventajas que no son de estilo:

- **El aislamiento de la 001 no se re-verifica.** Las 18 policies quedan byte por
  byte como están, con sus controles negativos ya corridos.
- **La regla se escribe una vez por tabla y no por rol.** `RESTRICTIVE` no
  necesita saber si quien escribe es entrenador o atleta: sobre un vínculo
  archivado no escribe nadie.
- **Se lee como lo que es.** "Además de todo lo anterior, nada se escribe sobre
  un vínculo archivado."

Seis tablas la necesitan —`program`, `mesocycle`, `session`, `prescription`,
`prescribed_set`, `logged_set`—, tres policies cada una: 18 nuevas.

**`athlete` no lleva ninguna, y es deliberado.** Si la llevara, archivar sería
irreversible: reactivar es un `UPDATE` sobre `athlete`, y la policy lo bloquearía
a él también. RLS no distingue por columna. Además deja algo correcto de arriba:
corregirle una falta de ortografía al nombre de alguien no debería exigir reabrir
el vínculo. Lo que se congela es el historial de entrenamiento, que es lo que la
spec llama "el historial".

**El argumento es la clave foránea al padre, no el id de la propia fila**, y esa
corrección se hizo al implementar. En un `INSERT` la fila todavía no existe, así
que un predicado que la busca por su id pregunta por algo que no está: `NOT
EXISTS` sobre nada contesta verdadero y la regla permite todo sin fallar nunca.
El padre sí existe y su clave viaja en la fila nueva.

`UPDATE` lleva las dos mitades. `USING` decide qué filas se pueden tocar y
`WITH CHECK` qué queda después: sin la segunda, una fila viva se podría mover a un
vínculo archivado.

Los seis helpers `app_vinculo_escribible_<tabla>(uuid)` son `SECURITY DEFINER`,
con `search_path` fijado y `EXECUTE` revocado de `PUBLIC`, y recorren la misma
cadena hacia `program` que ya recorren los `app_<rol>_ve_<tabla>` de la 0004. Se
generan del mismo mapa, por el mismo motivo que aquellos: escrita dos veces, la
cadena se desincroniza.

### Cómo se ve un rechazo desde afuera

Este párrafo decía que el silencio era el problema: que `UPDATE` y `DELETE`
devuelven cero filas y un endpoint que no mira el `rowcount` contesta `204`
mientras quien llamó cree que guardó. **Medido sobre la aplicación corriendo, es
falso**, y conviene dejar por qué.

SQLAlchemy cuenta las filas que una actualización del ORM espera tocar. Cuando la
policy filtra la fila, levanta `StaleDataError` en vez de seguir de largo: el dato
viejo queda intacto y no hay falso éxito. El riesgo era menor de lo que este plan
suponía.

Lo que sí estaba mal era la respuesta. Esos rechazos salían como `500`, que dice
"el servidor se rompió" cuando lo que pasó es "este vínculo está archivado", y un
frontend ante un `500` reintenta en vez de ofrecer reactivar.

Se traducen en `app/api/errores.py`, con manejadores globales y no con un `if` por
endpoint. La diferencia importa en una sola dirección: la garantía vive en las
policies, así que olvidarse de una traducción cuesta una respuesta fea sobre un
dato que igual está a salvo. Si el bloqueo viviera ahí, olvidarse sería una fuga.

El silencio sigue existiendo donde no hay ORM: un `db.execute(update(...))` a
nivel Core devuelve cero filas sin quejarse. Ninguna escritura de esta feature lo
hace, y vale saberlo antes de escribir la primera.

## 5. Cómo se verifica que no falte ninguna ruta

El recorrido de rutas de la 001 gana una dimensión. Hoy verifica, por cada ruta
descubierta, que sin credenciales dé 401, que sobre un recurso ajeno responda
como ante uno inexistente, y que sin `Active-Role` dé 400.

Se agrega: **toda ruta de escritura, sobre un vínculo archivado, tiene que ser
rechazada** — y rechazada quiere decir que el recurso no cambió, no que no hubo
excepción. El test compara el estado antes y después, porque el modo de falla es
justamente el silencioso.

La lista blanca sigue siendo explícita: una ruta nueva rompe el test hasta que
alguien decida en qué grupo va.

Verificado rompiéndolo, como T-016: sacar una de las 18 policies `RESTRICTIVE`
tiene que hacer fallar la suite. Si no falla, el test recorre menos rutas de las
que cree.

Fixtures nuevas: un vínculo archivado con historial cargado, uno pausado con
historial, y una persona con vínculos con cuatro entrenadores —tres archivados y
uno activo— para los criterios 7 y 8.

## 6. Tareas

1. Migración: `athlete.estado` con `CHECK`, backfill desde `is_active`, índice
   parcial nuevo, baja de `is_active`. Con `downgrade`.
2. Modelos al día y `docs/schema.sql` actualizado.
3. Migrar los consumidores de `is_active`: el listado del entrenador.
4. Dominio: qué transiciones de estado son válidas y cuáles no. Test primero
   (artículo IV).
5. Dominio: generación del token, su hash y el vencimiento. Test primero.
6. Migración: tabla `invitation` con el índice parcial de una sola pendiente.
7. RLS de `invitation`: el entrenador ve las de sus fichas, nadie más.
8. Los seis helpers `app_vinculo_escribible_<tabla>`, generados del mapa.
9. Migración: las 18 policies `RESTRICTIVE`.
10. `app_aceptar_invitacion`, con los cinco resultados y sus verificaciones.
11. Endpoints del entrenador: generar invitación, archivar, reactivar, pausar y
    reanudar.
12. Endpoint de aceptación, colgado del router de alta y no del de datos.
13. Traducción del bloqueo silencioso: toda escritura comprueba filas afectadas.
14. Fixtures: vínculo archivado, pausado, y la persona con cuatro entrenadores.
15. Recorrido de rutas con el eje nuevo, más la verificación por rotura.
16. Tests de los criterios 1 a 12 de la spec.
17. Actualizar `README.md`, el backlog de `sdd/README.md` y `docs/deploy.md` si
    la migración necesita un paso nuevo.

Diecisiete. El límite de `sdd/README.md` son veinte.

## 7. Deuda que este plan no paga

- **Nadie prueba que el link viaje seguro.** El token va por WhatsApp porque así
  trabaja el entrenador. Vence a los siete días y es de un solo uso, que es la
  mitigación; no es lo mismo que un canal seguro.
- **No hay límite de invitaciones.** Un entrenador puede regenerar el link mil
  veces. No es un riesgo hoy —requiere estar autenticado como entrenador— pero
  tampoco hay nada que lo frene.
- **El `downgrade` de la migración 1 no reconstruye la distinción.** Volviendo a
  `is_active`, `pausado` y `archivado` colapsan en `false` y no hay forma de
  saber cuál era cuál.
- **La 004 va a necesitar paginación** en el historial de un vínculo archivado, y
  `GET /athletes/{id}/sessions` sigue sin tenerla.
- **`invitation` no tiene política de retención.** Las aceptadas y las vencidas
  quedan para siempre.

Y una regla que este plan no bajó a ningún lado y la spec sí pedía: **archivar
invalida la invitación pendiente.** Faltaba entera, y la encontró el test del
criterio 11 — con el vínculo archivado, aceptar seguía asociando. Se resolvió
adentro de `app_aceptar_invitacion` (migración 0012) y no revocando al archivar,
porque así la garantía no depende de que todo camino futuro que archive se acuerde
de revocar.

Y un defecto que este plan no previó y apareció al implementarlo: **las policies
permisivas de la 0004 evaluaban `WITH CHECK` con el id de la fila nueva**, así que
el entrenador no podía insertar en ninguna de las cuatro tablas del editor —ni en
su propio espacio, ni con el vínculo activo—. Nadie lo había notado porque ningún
endpoint escribía ahí y el importador corre como dueño. Corregido en la migración
0010, con las tres direcciones medidas: el dueño inserta, un ajeno no, y sobre lo
archivado tampoco.
