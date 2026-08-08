# Plan — 001 Identidad y aislamiento por tenant

Cubre `spec.md` de esta carpeta. Proveedor de auth decidido en el ADR 0003.

La spec dice qué y por qué; acá está el cómo. Si algo de este plan contradice la
spec, gana la spec.

---

## 1. Modelo de identidad

El cambio de fondo: hoy cada rol trae su propia identidad pegada
(`coach.auth_user_id`, `athlete.auth_user_id`, cada uno con su `UNIQUE`). Eso
impide que una persona sea las dos cosas y, sobre todo, impide que tenga más de
un vínculo como atleta — que es lo que la spec exige.

Se introduce una tabla de identidad y los roles pasan a apuntarla.

```
app_user
  id             uuid pk
  auth_user_id   text unique not null      -- el `sub` del JWT
  email          citext unique not null
  display_name   text not null
  created_at     timestamptz not null
```

`coach` pierde `auth_user_id`, `email` y `display_name`, y gana
`user_id uuid not null unique references app_user`. El `UNIQUE` codifica la
regla de la spec: a lo sumo un perfil de entrenador por persona. Conserva
`locale` y `unit_system`, que son preferencias del rol, no de la persona.

`athlete` pierde `auth_user_id` y gana `user_id uuid null references app_user`.
Nulo significa **ficha sin cuenta todavía**, que es el caso central: el
entrenador arma el programa completo antes de que el atleta se registre.
`full_name` y `email` se quedan en `athlete` — son los datos que el entrenador
carga a mano cuando la persona todavía no existe como identidad.

La unicidad va como índice parcial, no como constraint:

```sql
CREATE UNIQUE INDEX athlete_coach_user_uq
  ON athlete (coach_id, user_id) WHERE user_id IS NOT NULL;
```

Parcial porque un entrenador puede tener varias fichas sin cuenta y en Postgres
los `NULL` no colisionan entre sí — un `UNIQUE` normal daría una falsa sensación
de estar cubierto. Es el mismo problema que resolvió el índice funcional de
`exercise`.

A diferencia de aquél, **este no va a `MANUALLY_MANAGED`**: SQLAlchemy expresa
índices parciales con `postgresql_where`, así que se declara en `models.py` y
autogenerate lo maneja. `athlete_coach_idx` ya funcionaba así. Lo que obliga a
`MANUALLY_MANAGED` no es ser parcial sino ser funcional —`COALESCE(...)` sobre
columnas— que el ORM no sabe expresar.

### Migración

Un solo revision, con `upgrade` y `downgrade` que revierten limpio — CI corre
`alembic upgrade head` seguido de `downgrade base` y falla si no.

El orden importa porque hay datos reales de la planilla en la base:

1. Crear `app_user`.
2. Poblarla desde `coach` (`auth_user_id`, `email`, `display_name`) y desde
   los `athlete` que tengan `auth_user_id` no nulo.
3. Agregar `user_id` a `coach` y `athlete`, poblarlos por el `auth_user_id`
   viejo, y recién ahí ponerle `NOT NULL` a `coach.user_id`.
4. Borrar las columnas viejas y sus constraints.

El `downgrade` reconstruye `auth_user_id` desde `app_user`. Pierde información
en un caso —una persona con dos vínculos como atleta no entra en el modelo
viejo— y eso se documenta en el docstring de la migración en vez de fingir que
es reversible del todo.

`docs/schema.sql` es documentación de referencia y no se aplica; se actualiza en
el mismo commit para que no mienta.

## 2. Verificación del token

Dependencia de FastAPI que valida el JWT contra el JWKS de Clerk. Sin SDK.

La parte que decide vive en `app/domain/`: recibe los claims ya decodificados y
la configuración esperada, y devuelve una identidad o un motivo de rechazo. No
importa `httpx` ni `fastapi`, así que se testea sin red — casos: token vencido,
`nbf` en el futuro, `azp` de otro origen, `iss` que no corresponde, algoritmo
inesperado.

El adaptador HTTP hace lo aburrido: traer el JWKS, cachearlo por `kid` con TTL,
y refrescar cuando aparece un `kid` desconocido. Sin ese refresco, una rotación
de claves del proveedor tira la app hasta el próximo deploy.

**`azp` es el que se olvida.** Sin validarlo, un token que Clerk emitió para
otro origen sirve contra esta API. Tiene criterio de aceptación propio (el 7)
justamente porque es el hueco más común de esta integración.

Errores distinguibles, como pide el criterio 6: vencido → `401` con un código que
el cliente puede leer para decidir si conviene renovar; inválido → `401` genérico
que no explica por qué.

## 3. Rol activo

El JWT dice quién sos, no desde dónde estás mirando. Una persona con los dos
roles tiene dos respuestas válidas y el sistema tiene que elegir una.

**El rol viaja en un header `Active-Role`**, obligatorio en todo endpoint de
datos. Sin prefijo `X-`: la convención quedó desaconsejada por la RFC 6648.

Las rutas quedan como están, sin duplicar lecturas por rol, y el cliente cambia
de rol sin cambiar de URL. El costo es que la elección del rol pasa a ser un dato
del request, y un dato puede faltar.

**No hay default. Nunca.** Es la regla que hace segura esta forma:

| Situación | Respuesta |
|---|---|
| Header ausente o vacío | `400`, sin tocar la base |
| Valor distinto de `coach` o `athlete` | `400` |
| La persona no tiene ese rol | `403` |
| La persona tiene ese rol | Se hace `SET LOCAL` de las dos variables de la sección 4 |

Elegir un rol "razonable" cuando el header no viene —el más amplio, o el único
que la persona tiene— es exactamente la falla que convierte a un atleta que
además es entrenador en una vía de escape del aislamiento. Ante la duda no se
adivina: se rechaza.

La dependencia que lee el header es la misma que abre la transacción y hace el
`SET LOCAL`. No hay forma de obtener una sesión de base sin haber declarado un
rol válido: si el header falta, la request muere antes de que exista la sesión.

### Cómo se hace difícil olvidarse

Con prefijos por rol, un endpoint nuevo tenía que elegir su grupo para existir.
Con header eso se pierde, así que hay que reponerlo. Cuatro capas, de la que más
sirve a la que menos:

Son dos mecanismos distintos de FastAPI y conviene no confundirlos: las
dependencias declaradas en el router **se ejecutan pero su valor no se inyecta**,
mientras que las declaradas en la firma del endpoint sí. Se usan las dos, para
cosas distintas.

**1. `require_tenant_context` va en el router.** El router de datos se declara
con `APIRouter(dependencies=[Depends(require_tenant_context)])`. Verifica el
token, resuelve la identidad, valida el header y hace el `SET LOCAL`. Corre en
toda ruta que cuelgue de ahí, incluso en las que no tocan la base. Olvidarse deja
de ser omitir una línea y pasa a ser crear un router aparte y montarlo — un acto
ruidoso, visible en cualquier review.

**2. `tenant_session` provee la sesión, y depende de la anterior.** El endpoint
que necesita base declara `db: OrmSession = Depends(tenant_session)`, y
`tenant_session` a su vez depende de `require_tenant_context`. FastAPI cachea las
dependencias por request, así que el contexto se resuelve una sola vez aunque se
lo referencie dos veces.

`get_db` deja de existir como dependencia pública. Un endpoint que quiera
saltearse el contexto no queda desprotegido: queda sin forma de obtener una
sesión. El acceso a datos y la resolución de tenant dejan de poder pedirse por
separado, y eso es lo que de verdad reemplaza a los prefijos por rol.

**3. Las policies fallan ruidosamente, no vacías.** Se usa
`current_setting('app.current_auth_user_id')` sin el segundo argumento, así que
una sesión sin contexto **tira error** en vez de devolver cero filas. Un
`SET LOCAL` olvidado deja de parecerse a "este usuario no tiene datos" y se
parece a lo que es: un bug. Con `missing_ok = true`, el mismo error se ve como
una lista vacía y puede pasar meses sin que nadie lo note.

Vale para las dos variables. El contrato completo —cuáles son, qué llevan y por
qué— está en la sección 4; acá sólo importa que ninguna tiene default.

El costo es que una consulta legítima fuera del ciclo de request —una migración,
un script de mantenimiento— revienta si no setea el contexto. Es el precio
correcto: obliga a ser explícito justo donde conviene serlo.

**4. El test verifica composición, no comportamiento.** Recorre `app.routes` y
afirma que `tenant_context` está en el árbol de dependencias de cada ruta de
datos, mirando `route.dependant`. No llama al endpoint: comprueba que la
protección está puesta. Un test de comportamiento se puede satisfacer por
accidente —un `400` que salió de una validación de Pydantic parece lo mismo que
el `400` del header ausente—; uno de composición, no.

## 4. Aislamiento

Dos capas, y la de abajo es la que manda.

### El contrato de la sesión

Cada request abre transacción y hace `SET LOCAL` de **dos** variables. Siempre
las dos, siempre en el mismo lugar, ninguna con default:

| Variable | Tipo | Valor |
|---|---|---|
| `app.current_auth_user_id` | `text` | El `sub` del JWT, tal cual lo devolvió la verificación de la sección 2 |
| `app.active_role` | `text` | `coach` o `athlete`, del header `Active-Role` |

**`active_role` y no `current_role`.** `CURRENT_ROLE` es una función del estándar
SQL y una palabra reservada de Postgres: `SET LOCAL app.current_role = 'coach'`
es un error de sintaxis, con prefijo y todo. Lo desagradable es que
`current_setting('app.current_role')` **sí** compila dentro de la policy, porque
ahí es un literal de texto — o sea que el DDL entra sin una queja y la app revienta
recién en runtime, en la línea que setea el contexto. Se puede sortear con
comillas dobles o con `set_config()`, pero las dos dejan una trampa para el
próximo que escriba la línea sin acordarse. Renombrar sale gratis y además espeja
el nombre del header.

`SET LOCAL` y no `SET`: el valor muere con la transacción, así que una conexión
reciclada del pool no arrastra el tenant del request anterior. Ese bug es
silencioso y devuelve datos de otro usuario.

**La variable lleva el `sub`, no `app_user.id`.** Parece un rodeo —el `id` es lo
que las policies terminan comparando— y es lo que evita un punto muerto: para
traducir `sub` a `app_user.id` hay que leer `app_user`, y esa lectura ocurre
*antes* de que exista contexto. Con RLS forzado sobre `app_user`, tira error. Sin
RLS sobre `app_user`, cualquier entrenador lee el email de todas las personas del
sistema, que es dato personal y no es de nadie más que de su dueño.

Con el `sub` el problema no se resuelve: desaparece. El `SET LOCAL` pasa a ser
función pura del token verificado y no toca la base, así que no existe ningún
instante en que haya una sesión abierta sin contexto.

El costo es un join más por policy, contra una columna `UNIQUE`. Y un corolario
de tipo que conviene tener presente: la variable es `text`, no `uuid`. Castearla
con `::uuid` es un error; el nombre lo dice para que se note al leerlo.

Las policies traducen con una función, escrita una sola vez:

```sql
CREATE FUNCTION app_current_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT u.id FROM app_user u
    WHERE u.auth_user_id = current_setting('app.current_auth_user_id')
$$;
```

`STABLE` y no `IMMUTABLE`: dentro de una transacción el valor no cambia, pero
depende del estado de la sesión. Declararla `IMMUTABLE` habilitaría al planner a
constant-foldear el resultado entre transacciones, que es exactamente la clase de
optimización que convierte esto en una filtración.

La policy de `app_user` **no** puede usar esta función: se llamaría a sí misma. Y
no falla lindo — el detector de recursión de Postgres
(`infinite recursion detected in policy`) mira referencias directas a la propia
tabla, y acá la referencia pasa por una función, así que no lo ve: la consulta se
va de pila y muere con `stack depth limit exceeded` (`54001`), un error que no
menciona ni RLS ni la policy. Peor síntoma, misma causa. Se escribe directo
contra `auth_user_id`.

### Dos policies por tabla, una por rol

No una policy con un `OR` adentro. Cada rol lleva la suya, nombrada
`<tabla>_as_<rol>`, y cada una arranca chequeando el rol activo:

```sql
CREATE POLICY athlete_as_coach ON athlete
    USING (current_setting('app.active_role') = 'coach'
           AND EXISTS (SELECT 1 FROM coach c
                       WHERE c.id = athlete.coach_id
                         AND c.user_id = app_current_user_id()));

CREATE POLICY athlete_as_athlete ON athlete
    USING (current_setting('app.active_role') = 'athlete'
           AND athlete.user_id = app_current_user_id());
```

Postgres combina las policies permisivas con `OR`, así que hay que garantizar que
nunca sean verdaderas las dos a la vez. Lo garantiza el chequeo de rol: la
variable tiene un solo valor.

El argumento en contra del `OR` es más fino de lo que parece, y conviene dejarlo
escrito bien porque la versión simple es falsa. Probado contra Postgres: un único
`USING (predicado_coach OR predicado_atleta)` sobre `athlete`, con las policies de
este plan, **no** filtró. El motivo es que el `EXISTS` contra `coach` corre bajo
la policy de `coach`, que a su vez filtra por rol y devuelve cero filas cuando el
rol activo es `athlete`. O sea que al `OR` lo salvó otra tabla.

Basta con aflojar esa otra policy para que el `OR` filtre. Escribiendo `coach`
como `USING (user_id = app_current_user_id())` —perfectamente razonable leída
sola: "el entrenador se ve a sí mismo"— la persona que es coach y además atleta
de otro pasa a ver, con rol `athlete`, las fichas de su propio espacio de
entrenador. Es el riesgo 2 de la spec, reproducido. Con las dos policies por rol
y *esa misma* policy floja de `coach`, no filtra.

Esa es la diferencia que importa: el `OR` es correcto sólo mientras todas sus
tablas vecinas sigan filtrando por rol, y esa dependencia no está escrita en
ningún lado ni la muestra un `\dp`. El gate propio no depende de nadie.

Partirlo en dos hace visible además lo que falta: `\dp` lista las policies por
tabla, y una tabla con `_as_coach` y sin `_as_athlete` se ve de un vistazo.

### `USING` no alcanza: hace falta `WITH CHECK`

`USING` filtra las filas que se leen, y las que ya existen para un `UPDATE` o un
`DELETE`. **No se aplica a un `INSERT`**: una fila nueva todavía no existe, así
que no hay nada que filtrar. Lo que gobierna un `INSERT` —y la fila resultante de
un `UPDATE`— es `WITH CHECK`.

Es la diferencia entre "no ves lo ajeno" y "no escribís sobre lo ajeno", y el
criterio de aceptación 4 —un atleta no registra una serie prescrita a otro— es lo
segundo. Con `USING` solo ese criterio no se cumple, aunque todos los tests de
lectura queden verdes.

`logged_set` es donde importa, porque es la única tabla que el atleta escribe:

```sql
CREATE POLICY logged_set_as_athlete ON logged_set
    USING (current_setting('app.active_role') = 'athlete'
           AND EXISTS (SELECT 1 FROM athlete a
                       WHERE a.id = logged_set.athlete_id
                         AND a.user_id = app_current_user_id()))
    WITH CHECK (
        current_setting('app.active_role') = 'athlete'
        -- la fila es mía...
        AND EXISTS (SELECT 1 FROM athlete a
                    WHERE a.id = logged_set.athlete_id
                      AND a.user_id = app_current_user_id())
        -- ...y la serie que estoy registrando me fue prescrita a mí
        AND EXISTS (SELECT 1
                    FROM prescribed_set ps
                    JOIN prescription pr ON pr.id = ps.prescription_id
                    JOIN session      s  ON s.id  = pr.session_id
                    JOIN mesocycle    m  ON m.id  = s.mesocycle_id
                    JOIN program      p  ON p.id  = m.program_id
                    WHERE ps.id = logged_set.prescribed_set_id
                      AND p.athlete_id = logged_set.athlete_id));
```

El segundo `EXISTS` es el criterio 4 entero. Sin él, el atleta manda su propio
`athlete_id` y un `prescribed_set_id` ajeno, y la fila entra: los dos predicados
de "es mío" pasan por separado; lo que falta verificar es que se correspondan
entre sí.

### Cómo llega cada tabla a su tenant

El artículo III (versión 1.1) exige que el camino esté declarado. Son dos
caminos, uno por rol, porque el rol activo cambia el predicado:

| Tabla | Rol `coach` | Rol `athlete` |
|---|---|---|
| `app_user` | la propia fila, por `auth_user_id` | ídem |
| `coach` | `user_id` | ninguno — ver abajo |
| `athlete` | `coach_id → coach.user_id` | `user_id` |
| `exercise` | `coach_id` propio, o `NULL` = catálogo global | global, o del entrenador que lo entrena |
| `program` | `coach_id → coach.user_id` | `athlete_id → athlete.user_id` |
| `mesocycle` | `program → coach` | `program → athlete` |
| `session` | `mesocycle → program → coach` | ídem hasta `athlete` |
| `prescription` | `session → … → coach` | ídem |
| `prescribed_set` | `prescription → … → coach` | ídem |
| `logged_set` | `prescribed_set → … → coach` | `athlete_id → athlete.user_id`, más el `WITH CHECK` de arriba |
| `movement_pattern` | referencia pura, sin RLS | ídem |

Cuatro decisiones que la tabla esconde:

**`app_user` sólo se ve a sí mismo, en los dos roles.** El entrenador no lee la
identidad de sus atletas porque no la necesita: `full_name` y `email` viven en
`athlete`, cargados a mano por él. Cuando la feature 003 vincule identidades con
fichas va a hacer falta abrir algo acá, y es mejor que sea una decisión de esa
feature y no un permiso que ya venía puesto.

Su `WITH CHECK (auth_user_id = current_setting('app.current_auth_user_id'))` es
además lo que hace segura la T-011: en el primer login la fila no existe todavía,
y la policy deja crear exactamente una —la propia— sin ningún `if` en la
aplicación.

**El atleta no lee `coach`.** Hoy ningún endpoint devuelve datos del entrenador.
El día que la 004 quiera mostrar "tu entrenador: X", eso es una policy nueva y
explícita, no un hueco que ya estaba abierto.

**Las cadenas se escriben completas, aunque Postgres las acorte.** Un `EXISTS`
contra `program` dentro de una policy de `mesocycle` ya viene filtrado por la
policy de `program`, porque RLS también se aplica a las subconsultas de una
policy. Es tentador y no se usa: la policy de `mesocycle` pasaría a leerse como
"cualquier programa", y su corrección dependería de que la de `program` exista y
de que el rol no esté exento. Un `\dp` no muestra esa dependencia. Escribir la
cadena entera cuesta cinco líneas por tabla y sobrevive a que alguien toque la
otra policy.

**Denormalizar `coach_id` sigue descartado.** Sería más rápido de consultar y
agrega una copia del tenant que hay que mantener consistente en cada insert; bajo
RLS, una copia desincronizada no es un dato feo, es una filtración. Los `EXISTS`
suben por claves foráneas ya indexadas, así que el costo es aceptable a esta
escala. Si alguna vez mide mal, denormalizar es una migración posterior — al
revés no.

### Los dos detalles que rompen esto en silencio

- **La app no se conecta como dueña de las tablas.** El dueño saltea RLS por
  default. Hace falta un rol de aplicación sin privilegios especiales, y el DSN
  de la app lo usa (T-007).
- **`FORCE ROW LEVEL SECURITY` en cada tabla**, además de `ENABLE`. Con `ENABLE`
  solo, el dueño sigue exento y los tests —que corren migraciones como dueño—
  pasarían sobre policies que en producción no se aplican igual.

**Dependencia obligatoria en la capa HTTP.** El router de datos se monta con la
dependencia que resuelve identidad y rol y hace el `SET LOCAL`. Olvidarse no deja
el endpoint abierto: lo deja sin variables de sesión, y `current_setting` sin el
segundo argumento tira error. El default es romper, no filtrar.

### Qué de todo esto está probado, y qué no

Esta sección se escribió dos veces. La primera versión era razonamiento; la
segunda es lo que quedó después de correrlo contra Postgres 16 en una base
desechable, con las migraciones reales aplicadas y un rol de aplicación sin
privilegios. Lo que el spike encontró:

- **`app.current_role` no compila.** Es palabra reservada. Esa es la razón del
  rename, y no se hubiera visto hasta implementar T-006.
- **`app_user` recursiva muere por pila, no por el detector de recursión.**
- **El `OR` no filtra por sí solo** en esta configuración; filtra en cuanto una
  policy vecina deja de gatear por rol. El argumento de arriba está reescrito
  sobre eso.

Verificado, cada uno con su control negativo —desarmar la decisión y comprobar
que la fuga aparece—:

| Qué | Resultado |
|---|---|
| Sesión sin contexto | error, no cero filas |
| Coach A pidiendo por id un recurso de B | cero filas, igual que un id inexistente |
| Persona atleta de dos entrenadores | ve sus dos fichas, nada de los espacios |
| Persona con los dos roles, rol `athlete` | no alcanza su propio espacio de coach |
| Catálogo global de `exercise` | visible; el de otro coach, no |
| Criterio 4 vía `WITH CHECK` | rechazado por la base |
| Criterio 4 **sin** el segundo `EXISTS` | **entra** — T-008b tiene motivo |
| `ENABLE` sin `FORCE`, dueño no superusuario | ve las cuatro filas |
| `ENABLE` + `FORCE`, mismo dueño | ve sólo las dos suyas |

Lo que **no** está probado y sigue siendo razonamiento: el rendimiento de los
`EXISTS` a escala (el spike tiene cuatro atletas), el comportamiento con el pool
de conexiones real, y todo lo de la capa HTTP, que es T-006.

## 5. Cómo se verifica que no falte ninguna ruta

El criterio 3 pide que el aislamiento valga para todos los endpoints, no para
los que alguien se acordó de testear. Se implementa como un test que recorre
`app.routes`:

- Toda ruta que no esté en una lista blanca explícita (`/health`, `/docs`,
  `/openapi.json`) tiene que responder `401` sin credenciales.
- Toda ruta que reciba un identificador de recurso se llama con credenciales del
  entrenador B sobre un recurso de A, y tiene que responder lo mismo que ante un
  identificador inexistente.
- **Toda ruta de datos tiene que responder `400` con credenciales válidas y sin
  header `Active-Role`.** Es lo que garantiza que la dependencia esté puesta:
  un endpoint que se olvidó de ella respondería `200` y el test lo caza.

La lista blanca es explícita a propósito: agregar una ruta nueva rompe el test
hasta que alguien decida conscientemente en qué grupo va.

Y el test de composición de la sección 3, capa 4: por cada ruta de datos,
`tenant_context` tiene que aparecer en su árbol de dependencias. Ese es el que
prueba que la protección **está**, no que parece estar.

Los cuatro se solapan a propósito. Ninguno es suficiente solo: el de
comportamiento se satisface por accidente, el de composición no ve si la policy
está bien escrita, y las policies no ven si alguien montó un router aparte.

Fixtures nuevas: dos entrenadores con un atleta cada uno, y una persona con
perfil de entrenador y ficha de atleta bajo su propio espacio, para los
criterios 9 a 11.

### El arnés de tests, que era el agujero más grande de todo esto

Los cuatro tests de arriba no valen nada si la fixture que los corre saltea lo
que pretenden verificar. Y lo salteaba.

`conftest.py` hacía `app.dependency_overrides[tenant_session] = lambda: db`.
`dependency_overrides` reemplaza una dependencia **y todo su subárbol**: en
cuanto T-006 cuelgue `require_tenant_context` de `tenant_session`, ese override
se lleva puestos la verificación del token, el header y el `SET LOCAL`, y la
suite entera queda verde sobre seguridad que nunca corrió.

No es una predicción. Colgándole a `tenant_session` una subdependencia que tira
`AssertionError` siempre, los 71 tests pasaban — T-016a incluido, porque afirma
que `tenant_session` está en el árbol de dependencias, y eso sigue siendo cierto
mientras el override se encarga de que la función no se ejecute. El test de
composición y el de comportamiento fallaban los dos por el mismo motivo.

La costura se bajó un nivel: se falsifica `open_session`, o sea de dónde sale la
conexión, y `tenant_session` corre entero. La regla que queda escrita es
**falsificar lo más externo que haga falta, nunca aquello que se quiere
verificar**. Cuando llegue T-006, lo que se falsifica es el proveedor de
identidad, no la resolución de tenant.

Con el mismo simulacro, la fixture nueva da 7 fallidos y 13 errores.

### Lo que sigue roto en el arnés, y lo choca T-014

La fixture `db` abre una transacción externa que se revierte al final, y el
`commit()` del endpoint sólo libera un `SAVEPOINT`. Medido: un
`SET LOCAL app.probe = 'primer_request'` sigue visible después del `commit()` y
lo ve el request siguiente de la misma transacción.

O sea que dos requests dentro de un mismo test comparten contexto de tenant.
Para la mayoría de los tests da igual —cada request setea el suyo y pisa el
anterior—, pero rompe justo los que importan: el que verifica que **una sesión
sin contexto tira error** no puede observarlo si la transacción ya trae contexto
de un request previo. Es el `SET LOCAL` fallando dentro del arnés por la misma
razón por la que existe en producción.

T-014 tiene que resolverlo antes que T-015 a T-017 se apoyen encima. La salida
esperada es un segundo cliente para los tests de seguridad, con transacción real
por request y limpieza por otra vía, conviviendo con la fixture rápida para los
funcionales. Decidirlo es parte de T-014, no de este plan.

## 6. Tareas

De la 6 y la 10 ya está hecha la parte estructural, antes de empezar el resto:
`get_db` dejó de ser dependencia pública, `tenant_session` es la única puerta a
la base desde un endpoint, y el test de composición (capa 4) está escrito y
muerde. Lo que falta de esas dos es el contenido: identidad, header y
`SET LOCAL`. Se adelantó a propósito para que el diff que agregue la seguridad
no venga mezclado con un refactor de seis firmas.

1. Migración: `app_user`, columnas nuevas, backfill, índice parcial, borrado de
   lo viejo. Con `downgrade`.
2. Modelos de SQLAlchemy al día; `MANUALLY_MANAGED` actualizado.
3. `docs/schema.sql` actualizado.
4. Dominio: resolución de claims a identidad, con sus tests. Primero el test
   (artículo IV).
5. Adaptador JWKS con caché por `kid` y refresco ante `kid` desconocido.
6. `tenant_context`: token → identidad → header `Active-Role` → `SET LOCAL` →
   cede la sesión. Los cuatro casos de la tabla, sin default. Retirar `get_db`
   como dependencia pública.
7. Rol de base de datos sin privilegios para la app; DSN y `.env.example`.
8. Migración de RLS: `ENABLE` + `FORCE` + policies por tabla.
9. Policy propia de `exercise` para el catálogo global.
10. Montar el router de datos con `dependencies=[Depends(tenant_context)]` y
    migrar los endpoints actuales a la sesión que provee.
11. Alta de entrenador en el primer login.
12. Crear atleta sin cuenta, dentro del espacio del entrenador.
13. Cierre de sesión que invalida el token anterior.
14. Fixtures de dos entrenadores y de la persona con doble rol.
15. Test de composición: `tenant_context` en el árbol de dependencias de cada
    ruta de datos. Más el de comportamiento sin credenciales.
16. Test que recorre las rutas: recurso ajeno, y sin header `Active-Role`.
17. Tests de los criterios 9 a 11.
18. Actualizar `README.md` y el backlog de `sdd/README.md`.

Dieciocho. El límite de `sdd/README.md` son veinte; si al implementar aparecen
más, es señal de que algo de acá era otra feature.

## 7. Deuda que este plan no paga

- Los tests de la cuaterna de sesiones y el `assert` de la fixture
  `session_detail` pasan trivialmente: la planilla tiene un solo programa. Son
  guarda, no evidencia.
- `conftest.py` importa `sqlalchemy`, `alembic` y `fastapi` a nivel de módulo,
  así que un clon limpio no corre los tests de dominio sin las dependencias de
  infraestructura. Contradice lo que dicen el README y el ADR 0002.
- La vista `weekly_volume` sigue sin consumidores; la analítica se calcula en
  Python trayendo todas las series a memoria.
- `GET /athletes/{id}/sessions` no tiene paginación.
