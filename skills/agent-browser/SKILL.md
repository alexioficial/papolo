---
name: agent-browser
description: "Smoke test de navegador post-deploy con Chrome headless. Cargala SIEMPRE despues de que un deploy llegue a 'running' en apps con UI (login, dashboards, formularios, CRUD), ANTES de reportar exito al usuario. Abre el preview URL, siembra una test DB con mock data, verifica el render real, corre login con credenciales sembradas, chequea console/errors JS, saca screenshot y emite PASS/FAIL. 'status: running' NO es prueba de que la app funciona."
---

# Skill: agent-browser — Smoke test de navegador post-deploy

Usa el CLI `agent-browser` (Vercel Labs, Chrome headless) para verificar que una app deployada **funciona de verdad** — no solo que el container arranco. Es la materializacion de la regla "si afirmas que funciona, tene la evidencia".

## El problema que resuelve

Papolo deployaba y reportaba "funciona" mirando `status: running`. Pero `running` solo dice que el container levanto. El login podia estar roto (DB no conecta), la pagina en blanco (falta `import '../app.css'`), o sin datos (seed nunca corrio). El usuario lo descubria y la credibilidad se perdia. Este smoke test cierra ese hueco: abre la app en un navegador real, interactua, y reporta PASS/FAIL con evidencia.

## Cuando usarla

- DESPUES de que `coolify_status` devuelva `running:*` en una app con UI (modo SIMPLE_TOOL o FULL_SYSTEM).
- ANTES de reportar el preview URL al usuario.
- Cuando el usuario reporta "el login no anda", "se queda pegado", "no muestra nada" — para reproducir y diagnosticar en vivo.

## Cuando NO usarla

- API pura sin frontend → basta `curl -sf $PREVIEW/api/health`.
- Respuestas conversacionales, research, tareas sin deploy.
- Antes de que el status sea `running` — no tiene sentido testear algo que no levanto.

## 0. Bootstrap del binario (best-effort, NO fatal)

```bash
command -v agent-browser >/dev/null 2>&1 || npm install -g agent-browser
agent-browser install >/dev/null 2>&1 || true   # baja Chrome for Testing
```

Si esto falla (permisos de npm global, o faltan libs de Chrome en el VPS como `libnss3`, `libgbm1`, `libatk1.0-0`), **NO bloquees la tarea**. Degrada con gracia:
1. Confirma que el deploy esta `running` y que `curl -sf $PREVIEW/api/health` responde OK.
2. Reporta al usuario: "El deploy esta arriba y el health check responde, pero no pude correr el smoke test visual porque Chrome headless no esta instalado en el VPS. Si queres smoke tests automaticos, instala `libnss3 libgbm1 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2` en el VPS."

No mientas diciendo que testeaste si no pudiste.

## PASO 0 (ahorra deploys): chequeo de ARRANQUE local antes de deployar

Cada deploy a Coolify cuesta build + push + 45-80s de espera. La causa nro 1 de deploys desperdiciados es deployar codigo que ni siquiera arranca (build roto, crash al boot). Eso lo catcheas LOCAL en segundos, sin deployar.

IMPORTANTE sobre el entorno del bot: **NO hay docker ni una DB local** en el shell del bot, y el `MONGODB_URI` de produccion esta filtrado. Asi que NO podes correr el full-stack con DB localmente. Pero SI podes verificar que la app **buildee y arranque** — que es lo que catchea los crashes de boot:

```bash
WS=/data/workspaces/<workspace>; cd "$WS"

# 1. Build local — catchea errores de build/sintaxis Svelte SIN deployar.
npm run build 2>&1 | tail -20      # si falla, fixea ACA, no deployando.

# 2. Arranque local — confirma que el server levanta y sirve (sin DB).
#    El /api/health NO debe requerir DB para responder (asi distingue "arranco" de "DB caida").
timeout 6 node build 2>&1 | head -5    # debe imprimir "Listening on http://0.0.0.0:3000"
```

Si esos dos pasan, el codigo arranca sano → el deploy no va a fallar por boot/build. (El testeo de login+DB+dashboard se hace despues contra la preview deployada, porque no hay Mongo local — ver abajo.) Si el deploy igual da `exited:unhealthy` pese a que arranca local, ver la nota en la skill `coolify-deploy`: suele ser transitorio del primer deploy.

## Smoke test por API con curl (METODO PRIMARIO Y CONFIABLE)

Chrome headless en el VPS del bot es **poco confiable** (faltan libs del sistema, el entorno es efimero y no siempre tenes apt para instalarlas). Por eso el smoke test **primario** es por API con curl — siempre funciona, no depende de Chrome, y verifica el sistema de punta a punta con la sesion real. agent-browser (secciones 3-6) es el extra "lindo" cuando Chrome arranca; el curl-smoke es el que NO podes saltearte.

Despues de deployar y sembrar (`POST /api/_seed`), corre esto contra la preview:

```bash
P="https://<short>.<dominio>"
# 1. login → captura la cookie de sesion en un cookie jar
curl -s -c /tmp/cj.txt -X POST "$P/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"email":"<email-sembrado>","password":"<pass-sembrada>"}'   # debe devolver ok:true
# 2. probar CADA endpoint protegido con la cookie — todos deben dar 2xx con datos reales
for ep in auth/me dashboard transactions accounts categories reports; do
  printf "%-14s " "$ep:"; curl -sf -b /tmp/cj.txt "$P/api/$ep" -o /dev/null && echo PASS || echo FAIL
done
# 3. render: la pagina protegida SSR-ea con datos (no en blanco, no template)
curl -sf -b /tmp/cj.txt "$P/dashboard" | grep -q "Dashboard" && echo "render PASS" || echo "render FAIL"
curl -sf "$P/login" | grep -q "Iniciar sesion" && echo "login-page PASS" || echo "login-page FAIL"
```

Criterio: TODOS PASS, con datos sembrados visibles en las respuestas (no listas vacias). Si el login da ok pero un endpoint da FAIL → diagnostica esa capa (DB/query), no el login. Esto reemplaza el smoke visual cuando Chrome no corre, y es suficiente para afirmar "funciona" con evidencia.

**Regla de oro:** NO deployas hasta que el smoke test LOCAL este en verde. El deploy es para publicar algo que YA sabes que funciona, no para descubrir si funciona.

## 1. Readiness — esperar que la preview resuelva (flujo contra preview)

El DNS de la preview (`https://<short>.<dominio>`) puede tardar en propagar tras el deploy. Espera antes de abrir el navegador:

```bash
PREVIEW="https://<short>.<dominio-preview>"   # del output de coolify_create_app
for i in $(seq 1 6); do
  curl -sf "$PREVIEW" >/dev/null 2>&1 && break
  echo "esperando preview... ($i/6)"; sleep 10
done
```

## 2. Sembrar la test DB con mock data (si la app usa DB)

La app usa una DB aislada (`MONGODB_DB_NAME=papolo_<short>`, seteada por `coolify_set_mongodb_env`). Esa es tu **test DB**: nunca testees contra datos reales ni contra una DB vacia (una app sin datos parece rota aunque ande).

**El seed corre DENTRO del container** (que tiene `MONGODB_URI`), disparado por un `curl` desde el shell. Vos nunca tocas el URI. El endpoint `/api/_seed` lo genera el sveltekit-expert/mongodb-expert, gated por `SEED_TOKEN`:

```bash
# Seteaste SEED_TOKEN y SEED_ENABLED=1 via coolify_set_env antes del deploy.
curl -s -X POST "$PREVIEW/api/_seed" -H "x-seed-token: <tu-seed-token>"
# Respuesta esperada: {"seeded": true, "users": N, ...}
```

**Credenciales sembradas (deterministas, siempre las mismas):**
- email: `test@papolo.dev`
- password: `Test1234!`

CRITICO: el endpoint de seed DEBE hashear el password con el MISMO bcryptjs que usa el login. Si el hash no coincide, el login falla con "credenciales invalidas" con las creds correctas y vas a diagnosticar la capa equivocada (auth) cuando el problema es el seed.

Si la app NO tiene DB/auth (landing, calculadora): salteá este paso y el login del paso 4.

## 3. Abrir la RAIZ `/` primero y verificar que NO esta en blanco

CRITICO: abri SIEMPRE la raiz `$PREVIEW` (sin `/login`), porque es la primera URL que toca el usuario. NUNCA saltes directo a `/login` — si lo haces, te perdes la pagina en blanco de la raiz (el bug nro 1). Razon comun de raiz en blanco: `redirect()` llamado en un `$effect`/cliente mata la hidratacion.

```bash
agent-browser open "$PREVIEW"          # la RAIZ, no /login
agent-browser wait --load networkidle
agent-browser snapshot --json          # accessibility tree con refs @e1, @e2...
```

Mira el snapshot DESPUES de hidratar:
- **Si el snapshot esta casi vacio** (1-2 nodos, sin form ni contenido) pese a que el HTML por curl tiene contenido → **PAGINA EN BLANCO por crash de hidratacion**. FAIL. Causa tipica: `redirect()` en cliente, o un error JS que mata el mount. Revisá `agent-browser errors --json` (paso 5) — ahi vas a ver la excepcion. curl NO atrapa esto (ve el HTML SSR), por eso el navegador es obligatorio.
- Si ves "Welcome to SvelteKit" / template default → FAIL.
- Si el screenshot sale sin estilos (HTML plano) → falta `import '../app.css'`.

## 4. Probar el flujo de REGISTRO (no solo login)

El registro es la primera accion real de un usuario nuevo y el form mas frecuentemente roto (redirect tras submit que no se sigue por `use:enhance` sin `update()`). Registra un usuario NUEVO via la UI y verifica que **redirige y muestra exito**:

```bash
agent-browser open "$PREVIEW/register"   # o segui el link "Registrate" desde la raiz
agent-browser wait --load networkidle
agent-browser snapshot --json
# llena el form con un email random nuevo
agent-browser fill @e<name>  "Smoke Test"
agent-browser fill @e<email> "smoke+$(date +%s)@papolo.dev"
agent-browser fill @e<pass>  "Test1234!"
# si hay confirmar password, llenalo igual
agent-browser click @e<submit>
agent-browser wait --load networkidle
agent-browser get url                    # DEBE ser /dashboard (o pagina logueada), NO seguir en /register
agent-browser snapshot --json            # confirmar que entro
```

Si tras el submit la URL SIGUE en `/register` y no hay mensaje de exito ni de error → el `use:enhance` no esta llamando `update()`/`applyAction()` y se traga el redirect. **FAIL** — el usuario real veria "no pasa nada", reintentaria, y le diria "ya estas registrado". Reportalo y fixea (ver sveltekit-expert: enhance con `update()`).

## 4b. Login con las credenciales sembradas

Usa el usuario DEMO sembrado que TIENE datos (no un admin vacio), asi verificas que la data se ve. Del snapshot de `/login` saca los refs:

```bash
agent-browser open "$PREVIEW/login"
agent-browser fill @e<email>  "test@papolo.dev"
agent-browser fill @e<pass>   "Test1234!"
agent-browser click @e<submit>
agent-browser wait --load networkidle
agent-browser get url                    # DEBE haber cambiado a /dashboard
agent-browser snapshot --json            # confirmar dashboard CON datos sembrados visibles
```

Si despues del submit seguis en el login o ves "Credenciales invalidas" CON las creds correctas → casi siempre es **conexion a DB**, no el codigo de auth. Verificá `curl -sf $PREVIEW/api/health`. Si la URL no cambia pero tampoco hay error → es el mismo bug de `use:enhance` sin `update()`. NO debuggees el form a ciegas.

## 5. Chequear errores JS y consola

```bash
agent-browser errors --json            # excepciones JS no capturadas
agent-browser console --json           # warnings/errores de consola
```

`errors` con contenido = **FAIL**. Hay un bug de runtime que el usuario veria.

## 6. Evidencia visual + cerrar

```bash
agent-browser screenshot deploy-smoke.png --full
agent-browser close || true            # SIEMPRE cerrar — sino queda daemon huerfano
```

## Criterio PASS / FAIL

| Señal | PASS si | FAIL si |
|---|---|---|
| raiz `/` hidratada | snapshot con form/contenido real tras networkidle | snapshot casi vacio = blank por crash de hidratacion (curl NO lo ve) |
| `errors` (en CADA pagina) | array vacio | hay excepciones JS no capturadas |
| registro | tras submit la URL cambia a /dashboard + entra | sigue en /register sin exito ni error = `enhance` sin `update()` |
| login con demo user | post-submit URL = /dashboard, datos sembrados visibles | sigue en login, o dashboard vacio pese a seed |
| datos del dominio | se ven los registros sembrados | listas vacias pese a estar sembrado |
| screenshot | render visible y con estilos | en blanco / HTML sin CSS |

PASS = TODAS las señales aplicables en verde. Verifica raiz + registro + login, no solo login. Recien ahi reporta el preview URL al usuario.

## En FAIL — NO reportes exito

1. NO digas que funciona. Carga `debugging-systematic`.
2. Aisla la capa que falla de abajo hacia arriba: DB (`/api/health`) → seed → query → render. El bug casi siempre esta mas abajo de lo que parece.
3. Patron mas comun: **login falla con creds correctas → es conexion DB, no auth.**
4. Si estas en el loop LOCAL: fixea, `npm run build`, relanza `node build`, re-testea. SIN deploy. Esto es lo que ahorra deploys — itera local hasta verde.
5. Maximo 2 reintentos del mismo approach. Si sigue fallando, reporta al usuario con el screenshot y tu diagnostico concreto, y pedi instrucciones.

## Cheat sheet

1. **Chequeo de arranque LOCAL antes de deployar**: `npm run build` + `timeout 6 node build` (debe decir "Listening on 3000"). Catchea build roto / crash al boot sin gastar un deploy. NO hay docker ni Mongo local, asi que el DB-flow se testea despues contra la preview.
2. **El smoke test PRIMARIO es por API con curl** (login → cookie → cada endpoint → render). Siempre funciona, no depende de Chrome. agent-browser es el extra cuando Chrome arranca.
3. Sembra la test DB con mock data ANTES de testear — app vacia parece rota.
4. Si el login da ok pero un endpoint da FAIL → es esa capa (DB/query), no el login.
5. agent-browser (Chrome) es best-effort: si no instala/no arranca por libs del sistema, NO bloquees — el curl-smoke ya cubre el caso. No mientas diciendo que testeaste visual si no pudiste.
6. El seed corre dentro del container via `curl /api/_seed` — vos nunca tocas el MONGODB_URI de produccion.
7. Si usas agent-browser: `wait --load networkidle` antes de `snapshot`, `--json` para los refs, `errors` vacio requisito de PASS, screenshot `--full`, `close` al final.
8. PASS = login + todos los endpoints con datos sembrados + render con contenido real. Recien ahi reporta el URL.

## Formato de salida

```
## Smoke test de navegador
- Preview: {url}
- Seed: {OK / N records / sin DB}
- Render inicial: [PASS/FAIL] {detalle}
- Login: [PASS/FAIL/N-A] {detalle}
- Datos del dominio: [PASS/FAIL] {detalle}
- Errores JS (console/errors): [PASS/FAIL] {detalle}
- Screenshot: deploy-smoke.png

## Resultado
PASS — la app funciona, reporto el URL al usuario.
  / FAIL — {causa raiz diagnosticada} → {accion}
```

## Tools disponibles
read_file, write_file, list_dir, shell (para correr agent-browser y curl), load_skill
