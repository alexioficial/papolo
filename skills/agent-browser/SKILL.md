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

## 1. Readiness — esperar que la preview resuelva

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

## 3. Abrir y verificar render real

```bash
agent-browser open "$PREVIEW"
agent-browser wait --load networkidle
agent-browser snapshot --json          # accessibility tree con refs @e1, @e2...
```

Mira el snapshot: ¿hay contenido real del sistema? Si esta vacio, o ves "Welcome to SvelteKit" / "Edit this file" / template default → **FAIL** (la pagina raiz no tiene contenido real). Si el screenshot sale sin estilos (HTML plano) → falta `import '../app.css'`.

## 4. Login con las credenciales sembradas (si hay auth)

Del snapshot saca los refs de los inputs (email, password) y el boton submit:

```bash
agent-browser fill @e<email>  "test@papolo.dev"
agent-browser fill @e<pass>   "Test1234!"
agent-browser click @e<submit>
agent-browser wait --load networkidle
agent-browser snapshot --json          # confirmar que entro al dashboard
```

Si despues del submit seguis en el login o ves "Credenciales invalidas" CON las creds correctas → casi siempre es **conexion a DB**, no el codigo de auth. Verificá `curl -sf $PREVIEW/api/health` (deberia mostrar el estado de la DB). NO te pongas a debuggear el form de login.

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
| snapshot inicial | nodos con texto real del dominio | vacio, o "Welcome to SvelteKit" / template default |
| `errors` | array vacio | hay excepciones JS no capturadas |
| login (si hay auth) | post-submit el snapshot muestra estado autenticado / dashboard | sigue en login o "Credenciales invalidas" con creds correctas |
| datos del dominio | se ven los registros sembrados | listas vacias pese a estar sembrado |
| screenshot | render visible y con estilos | en blanco / HTML sin CSS |

PASS = TODAS las señales aplicables en verde. Recien ahi reporta el preview URL al usuario.

## En FAIL — NO reportes exito

1. NO digas que funciona. Carga `debugging-systematic`.
2. Aisla la capa que falla de abajo hacia arriba: DB (`/api/health`) → seed → query → render. El bug casi siempre esta mas abajo de lo que parece.
3. Patron mas comun: **login falla con creds correctas → es conexion DB, no auth.**
4. Fixea desde codigo/config, redeploya, y volve a correr el smoke test.
5. Maximo 2 reintentos. Si sigue fallando, reporta al usuario con el screenshot y tu diagnostico concreto, y pedi instrucciones.

## Cheat sheet

1. Bootstrap best-effort — si Chrome no instala, degrada con gracia, no bloquees.
2. Readiness loop (`curl` con reintentos) ANTES de abrir el navegador (DNS tarda).
3. Sembra la test DB con mock data ANTES de testear — app vacia parece rota.
4. El seed corre dentro del container via `curl /api/_seed` — vos nunca tocas el MONGODB_URI.
5. Creds sembradas siempre `test@papolo.dev` / `Test1234!` — hash con el MISMO bcryptjs que el login.
6. `wait --load networkidle` SIEMPRE antes de `snapshot`.
7. Usa `--json` para parsear los refs (@e1) de forma confiable.
8. `errors` vacio es requisito de PASS.
9. Screenshot `--full` como evidencia.
10. `agent-browser close` al final, siempre.
11. En FAIL: diagnostica DB primero (`/api/health`), nunca el login a ciegas.

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
