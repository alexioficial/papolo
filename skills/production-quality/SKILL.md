---
name: production-quality
description: Enforce code production-ready, completo, sin placeholder, con todos los estados. Cargala cuando el subagent sveltekit-expert o fastapi-expert implemente features, para verificar que el codigo es completo y no deja "TODO", "FIXME", "placeholder" ni implementaciones a medias. Previene el problema de "primera build en blanco".
---

# Skill: Production Quality Enforcer

## Cuando usarla
- **SIEMPRE** despues de que un subagent termine de implementar codigo, ANTES de buildear o deployar
- Cuando el subagent sveltekit-expert entrega archivos — verifica que sean completos
- Cuando veas "Dashboard works!", "Welcome to SvelteKit", o template por defecto en el build
- Cuando el codigo compile pero la pagina se vea en blanco o vacia

## Cuando NO usarla
- Tasks exploratorias, debugging, research
- Cuando solo se lee codigo sin modificarlo

## Problema que resuelve

Papolo suele generar codigo que:
1. Deja el template default de SvelteKit (`Welcome to SvelteKit`) porque el subagent "scaffoldea" pero no implementa
2. No reemplaza el contenido de `+page.svelte` con el sistema real
3. Olvida agregar `import '../app.css'` en layout raiz → Tailwind 4 no funciona → pagina en blanco sin estilos
4. Deja placeholders "TODO: implement", "FIXME", "// add logic here"
5. Implementa CRUD pero sin UI → el usuario ve una pagina blanca
6. La ruta raiz `/` no tiene contenido real
7. No implementa empty states → pagina vacia parece rota

## Procedimiento

### Fase 1: Scan de Archivos Generados

Corre este checklist contra el workspace. Si FALLA cualquier item, NO buildes ni deployes. Fixea primero.

#### 1.1 Archivos criticos (deben EXISTIR con contenido REAL)
- [ ] `src/routes/+layout.svelte` — debe tener `{@render children()}`, `import '../app.css'`
- [ ] `src/routes/+page.svelte` — debe tener contenido del sistema, NO template welcome
- [ ] `src/routes/+error.svelte` — pagina de error personalizada
- [ ] `src/app.css` — imports de Tailwind 4 y custom tokens
- [ ] `Dockerfile` — SIEMPRE presente con build_pack="dockerfile"

#### 1.2 Scan de Placeholders (BUSCAR y ELIMINAR)
Busca estos strings en los archivos generados:
```
"Welcome to SvelteKit"
"Welcome to Svelte"
"Edit this file"
"TODO" / "FIXME" / "HACK"
"// add logic"
"// implement"
"<!-- implement -->"
"placeholder"
"Lorem ipsum"
"Dashboard works"
"Get started"
"Visit kit.svelte.dev"
"documentation"
```

SI ENCUENTRAS alguno:
1. Identifica que archivo y que linea
2. Reemplazalo con el contenido real del sistema
3. Si es la pagina raiz (`+page.svelte`), reescribela COMPLETAMENTE con el contenido del sistema

#### 1.3 Verificacion de Implementacion Real
- [ ] `+page.svelte` renderiza DATOS REALES (no solo "Hola mundo" o template)
- [ ] Si hay DB: la page load function llama a la DB y pasa `data` a la pagina
- [ ] Hay al menos un componente del sistema (formulario, lista, dashboard)
- [ ] Los forms tienen `action` o `use:enhance` real, no solo HTML estatico
- [ ] Los botones/elementos interactivos tienen eventos reales

### Fase 2: Build Verification

Antes de deployar, corre el build local y verifica:

```bash
cd <workspace>
pnpm build  # o npm run build
```

#### 2.1 Build Exitoso?
- [ ] `pnpm build` termina sin errores (exit code 0)
- [ ] NO solo "build successful" — verifica que los archivos compilados existen

#### 2.2 Build Output Check
- [ ] `build/server/` contiene entry.js o index.js
- [ ] `build/client/` contiene los archivos del bundle

Si el build falla, NO deployes. Lee el error, fixea, rebuild.

#### 2.3 Static Check (SvelteKit)
```bash
pnpm check  # svelte-check
```
Si hay errores de tipos, fixea. Si solo warnings, puede pasar.

### Fase 3: Dockefile Verification

- [ ] `Dockerfile` existe en la raiz
- [ ] Usa `FROM node:20-slim` (para SvelteKit) o `FROM python:3.12-slim` (para FastAPI)
- [ ] Tiene multi-stage build (builder + runtime)
- [ ] El `CMD` coincide con el puerto correcto:
  - SvelteKit: `CMD ["node", "build"]` con `PORT=3000`
  - FastAPI: `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`
- [ ] Tiene cache buster (comentario unico con fecha-hora)
- [ ] `.dockerignore` existe

### Fase 4: Data Verification

Si el sistema usa DB:
- [ ] `src/lib/server/db.ts` (o equivalente) existe con lazy connection pattern
- [ ] Lee `MONGODB_URI` de `process.env` (NO hardcodeado)
- [ ] NO conecta al startup — solo via `getDb()` on-demand
- [ ] `coolify_set_mongodb_env` fue llamado antes del primer deploy

### Fase 5: Auth Verification (si aplica)

- [ ] `hooks.server.ts` existe con handle de auth
- [ ] Las rutas protegidas redirigen a login si no hay sesion
- [ ] Las rutas de admin rechazan si el rol no es admin
- [ ] Login/register forms tienen validacion server-side
- [ ] Passwords hasheados con bcrypt (no plain text)

### Fase 6: UI Verification

- [ ] La pagina carga sin errores de consola
- [ ] Los estilos Tailwind se ven correctos (no pagina en HTML plano)
- [ ] Empty states: "No hay X" con boton para crear
- [ ] Error states: mensaje claro si algo falla
- [ ] Loading states: skeleton o spinner mientras carga
- [ ] Responsive: se ve bien en mobile

### Fase 7: Anti-Stupid Checklist (lo que Papolo hace mal tipicamente)

**Check especifico para cada deploy:**
- [ ] `+page.svelte` raiz NO es el template de SvelteKit — si lo es, BORRALO y ESCRIBE el contenido real
- [ ] El layout raiz tiene `{@render children()}` — sin esto, pagina en blanco
- [ ] `import '../app.css'` en layout raiz — sin esto, Tailwind no carga, pagina sin estilos
- [ ] No hay `onMount` para fetch de datos — usa load functions de SvelteKit
- [ ] El build produce `build/server/` y `build/client/` con contenido real
- [ ] El Dockerfile usa el package manager correcto (pnpm vs npm segun lockfile)
- [ ] Las env vars necesarias estan seteadas en Coolify (MONGODB_URI, etc)
- [ ] **NO hay `redirect()` llamado desde cliente** (mata hidratacion → pagina en blanco). Grep: `grep -rn "redirect(" src/routes --include="*.svelte"` debe dar VACIO. `redirect()` solo en `+*.server.ts`/`+page.ts` load/actions. Para nav client usar `goto()`.
- [ ] **Todo `use:enhance` con callback custom llama `update()` o `applyAction()`** (sino se traga redirects/exito). Grep: por cada `grep -rln "use:enhance={(" src/routes`, abri el archivo y confirma que el callback async hace `await update()` o `applyAction(result)`. Si no, el registro/login "no hace nada" al exito.

## Si algo falla en Fase 6-7

**NO reintentes deploy con los mismos args.** Lee el error, identifica la causa:
- "Pagina en blanco" → falta `{@render children()}` o falta `import '../app.css'`
- "Template default" → +page.svelte no fue reemplazado
- "Build falla" → leer el error exacto, fixear, rebuild
- "502 Bad Gateway" → el puerto del CMD no coincide con ports_exposes de Coolify
- "Contenido viejo" → cache buster en Dockerfile. Si ya tiene, 1 reintento mas. Si sigue, PARA.

**Maximo 2 reintentos.** Si tras 2 intentos el build sigue mal, reporta al usuario y pedi instrucciones. NO entres en loop de deploy infinito.

## Formato de salida
```
## Production Quality Check
- [PASS/FAIL] Archivos criticos
- [PASS/FAIL] Placeholders scan
- [PASS/FAIL] Build local
- [PASS/FAIL] Dockerfile
- [PASS/FAIL] Auth
- [PASS/FAIL] UI states

## Archivos fixeados
- {path}: {que se cambio}

## Resultado
APTO PARA DEPLOY / REQUIERE FIXES
```

## Tools disponibles
read_file, write_file, list_dir, shell (para build y checks), grep (via shell) para scan de placeholders
