# ADR 0003 — Clerk como proveedor de autenticación

Fecha: 2026-08-07 · Estado: aceptado

## Contexto

El proyecto no escribe autenticación propia: el proveedor es externo y el backend
se limita a verificar el JWT. Queda elegir cuál.

`docs/PLAN.md` sugería Clerk o `fastapi-users`, y avisaba en la misma tabla que
el ecosistema de auth se había movido y que convenía verificar el estado al
momento de arrancar en vez de fiarse de esa lista. Se verificó en agosto de 2026
y el aviso resultó justificado.

Lo que se encontró:

- **`fastapi-users` está en modo mantenimiento.** Último release en marzo de
  2026; sólo parches de seguridad y de dependencias, sin features nuevas.
- **Clerk subió su tier gratis de 10.000 a 50.000 usuarios** en febrero de 2026.
  Cobra por *monthly retained user*, no por activo: una persona recién cuenta
  cuando vuelve a la app al menos 24 horas después de registrarse.
- **Supabase Auth da 50.000 MAU gratis** y expone `auth.uid()` dentro de las
  policies de RLS, pero **las bases del plan gratuito se pausan tras siete días
  de poca actividad**: se apaga la infraestructura y los datos quedan
  inaccesibles hasta reactivarla a mano.

Restricciones que impone este proyecto: el backend es FastAPI y verifica el
token sin SDK; el deploy apunta a Railway o Fly; y —lo que más pesa— el retorno
de este proyecto está en el portfolio, no en la facturación (`PLAN.md`, sección
1), así que la demo tiene que estar viva el día que alguien la abra.

## Opciones

**`fastapi-users`.** Control total y sin costo. Descartada dos veces: está en
mantenimiento, y es autoalojada, que es exactamente lo que la decisión de no
escribir auth propia descarta. Escribir hash de contraseñas y flujos de recuperación no impresiona a
nadie y consume dos semanas.

**Supabase Auth.** El argumento fuerte es que `auth.uid()` hace las policies de
RLS más directas, y el aislamiento por tenant es la razón de existir de todo
este trabajo. El
costo es que ata la base de datos al mismo proveedor que la identidad, y que el
plan gratuito pausa la demo. Evitar la pausa cuesta USD 25 mensuales para
siempre, contra un proyecto que por diseño no factura. Los *keep-alive* que
circulan —un cron que pinguea la base— resuelven el síntoma y quedan mal en un
repo cuyo objetivo es mostrar criterio.

**Better Auth.** TypeScript primero; los puentes a Python son paquetes de
comunidad. El backend es lo que mira un revisor y no conviene meterle una
dependencia de terceros justo en el borde de auth.

**Clerk.** Tier gratis holgado para el horizonte del proyecto, SDK de React para
el frontend y verificación manual del JWT documentada para el backend.

## Decisión

Clerk, verificando el token contra el JWKS del proveedor
(`<Frontend API URL>/.well-known/jwks.json`), validando algoritmo, `exp`, `nbf`
y `azp`. Sin SDK de Clerk en el backend.

Dos cosas que **no** se delegan al proveedor, porque son del dominio:

**El link de invitación es nuestro.** El diseño exige que la ficha del atleta
exista, con su programa entero cargado, antes de que el atleta tenga cuenta.
Usar las invitaciones de Clerk obligaría a que la identidad venga primero, que
es al revés de como trabajan los entrenadores. El token de invitación se genera
y se valida acá; Clerk aparece recién cuando el atleta se registra y se asocia
su identidad a la ficha existente. El flujo completo vive en el ciclo de vida
del vínculo; esta decisión se toma acá porque condiciona qué se le delega al
proveedor.

**Los roles son nuestros.** Clerk tiene organizations y roles, pero el modelo
entrenador/atleta —incluida la persona que es las dos cosas, y el atleta con
varios entrenadores— se decidió con cuidado. Clerk responde
"quién sos"; qué podés hacer lo resuelven la tabla de identidad y RLS.

El aislamiento por tenant se implementa con `SET LOCAL` de una variable de
sesión por request y policies que la leen con `current_setting()`. Es el mismo
RLS que daría `auth.uid()`, no depende del proveedor, y deja el mecanismo a la
vista en vez de detrás de una función mágica.

## Consecuencias

**A favor.** El costo de auth es cero en el horizonte realista del proyecto. La
identidad y la base de datos quedan desacopladas: mover la base de Railway a Fly
no toca auth, y cambiar de proveedor de auth no toca la base. El backend no
maneja contraseñas, sesiones ni recuperación de cuenta. Las policies de RLS
quedan escritas de forma portable.

**En contra.** Hay lock-in en el lado de la identidad: migrar a otro proveedor
implica remapear los `sub` de todos los usuarios. La verificación manual del
JWT es código nuestro y hay que testearlo — en particular la validación de `azp`,
que es fácil de omitir y es la que impide que un token emitido para otro origen
sirva acá. El modelo de cobro por MRU es poco común y conviene revisarlo si
alguna vez el proyecto escala, porque no se compara directo con el MAU del resto
del mercado.

**Lo que no se resolvió.** Si el proyecto alguna vez necesita storage propio
—videos de ejercicios subidos por el entrenador, hoy `Exercise.video_url` apunta
afuera— la comparación con Supabase habría que rehacerla, porque ahí entra a
pesar todo lo que trae además de auth.

## Referencias

- [Project Pausing — Supabase Docs](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Manual JWT verification — Clerk Docs](https://clerk.com/docs/guides/sessions/manual-jwt-verification)
- [`fastapi-users` en PyPI](https://pypi.org/project/fastapi-users/)
