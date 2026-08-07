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
de estar cubierto. Es el mismo problema que ya resolvió el índice funcional de
`exercise`, y va escrito a mano en la migración por el mismo motivo: agregar su
nombre a `MANUALLY_MANAGED` en `models.py`.

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
| La persona tiene ese rol | Se resuelve el tenant y se hace `SET LOCAL` |

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
`current_setting('app.current_user_id')` sin el segundo argumento, así que una
sesión sin contexto **tira error** en vez de devolver cero filas. Un `SET LOCAL`
olvidado deja de parecerse a "este usuario no tiene datos" y se parece a lo que
es: un bug. Con `missing_ok = true`, el mismo error se ve como una lista vacía y
puede pasar meses sin que nadie lo note.

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

**RLS en Postgres.** Cada request abre transacción y hace `SET LOCAL` de la
identidad y el rol resueltos. Las policies leen esas variables con
`current_setting('app.current_user_id', true)`. `SET LOCAL` y no `SET`: el valor
muere con la transacción, así que una conexión reciclada del pool no arrastra el
tenant del request anterior. Ese bug es silencioso y devuelve datos de otro
usuario.

Dos detalles que rompen esto en silencio si se pasan por alto:

- **La app no se conecta como dueña de las tablas.** El dueño saltea RLS por
  default. Hace falta un rol de aplicación sin privilegios especiales, y el DSN
  de la app lo usa.
- **`FORCE ROW LEVEL SECURITY` en cada tabla**, además de `ENABLE`. Con `ENABLE`
  solo, el dueño sigue exento y los tests —que corren migraciones como dueño—
  pasarían sobre policies que en producción no se aplican igual.

**Cómo llega cada tabla a su tenant.** El artículo III (versión 1.1) exige que
esté declarado, porque sólo tres tablas tienen `coach_id` propio:

| Tabla | Camino al entrenador |
|---|---|
| `coach` | Es el tenant |
| `athlete` | `coach_id` |
| `program` | `coach_id` |
| `exercise` | `coach_id`, o `NULL` = catálogo global |
| `mesocycle` | `program` |
| `session` | `mesocycle → program` |
| `prescription` | `session → mesocycle → program` |
| `prescribed_set` | `prescription → … → program` |
| `logged_set` | `prescribed_set → … → program`, y además `athlete_id` para el rol atleta |
| `movement_pattern` | Referencia pura, sin RLS |

Las cinco de abajo llevan policy con `EXISTS` subiendo la cadena, **no una
columna `coach_id` denormalizada**. Denormalizar sería más rápido de consultar y
agrega una copia del tenant que hay que mantener consistente en cada insert; con
RLS, una copia desincronizada no es un dato feo, es una filtración. Los `EXISTS`
suben por claves foráneas ya indexadas, así que el costo es aceptable a esta
escala. Si alguna vez mide mal, denormalizar es una migración posterior — al
revés no.

`exercise` lleva policy propia: `coach_id IS NULL` es el catálogo global y tiene
que seguir siendo visible para todos los entrenadores.

**Dependencia obligatoria en la capa HTTP.** El router de datos se monta con la
dependencia que resuelve identidad y rol y hace el `SET LOCAL`. Olvidarse no
deja el endpoint abierto: deja el endpoint sin variables de sesión, y las
policies devuelven cero filas. El default es romper, no filtrar.

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
