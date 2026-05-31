---
name: coolify-deploy
description: Como deployar un proyecto a Coolify con las tools de deploy. Define que build_pack usar segun el stack (Python/Rust/Go -> Dockerfile obligatorio, NUNCA docker-compose; SvelteKit/Node -> adapter-node + nixpacks). Cargala antes de llamar coolify_create_app por primera vez en una tarea de deploy.
---

# Skill: coolify-deploy

## Cuando usarla
- Vas a llamar `coolify_create_app` por primera vez
- El usuario pide "deployalo", "subilo a coolify", "haceme un preview", etc
- Necesitas preparar un proyecto para producir un container que arranque ok

## Cuando NO usarla
- Solo vas a hacer `coolify_status` o `coolify_set_env` sobre una app ya existente (no necesitas re-preparar el repo)
- El usuario solo pidio scaffolding sin deploy

## Reglas absolutas

| Stack | build_pack | Notas |
|---|---|---|
| **Python** (FastAPI, scripts, etc) | **`dockerfile`** | Escribi un Dockerfile a mano. NUNCA docker-compose. |
| **Rust** (Actix, Axum, etc) | **`dockerfile`** | Idem. Multi-stage builder + slim runtime. |
| **Go** | **`dockerfile`** | Idem. |
| **Node / SvelteKit / Next** | **`nixpacks`** | Solo si configuras adapter-node (ver abajo). |
| **Static site** (HTML+JS, build output) | **`static`** | Si tenes pre-build, podes usar este. |

**Critico**: para Python/Rust/Go, jamas pases `build_pack="docker-compose"` ni escribas un `docker-compose.yml`. Solo Dockerfile.

## Procedimiento por stack

### SvelteKit (y Node en general)
SvelteKit con `adapter-auto` genera output ambiguo y nixpacks no sabe arrancarlo. **Siempre** cambia a `adapter-node` antes de deployar.

1. Verifica que existe `svelte.config.js`. Si scaffoldeaste con `pnpm create svelte` / `pnpm dlx sv create`, viene por default con `adapter-auto`.
2. Agregar la dep:
   ```bash
   pnpm add -D @sveltejs/adapter-node
   ```
3. Sobrescribir `svelte.config.js`:
   ```js
   import adapter from '@sveltejs/adapter-node';
   import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

   export default {
     preprocess: vitePreprocess(),
     kit: { adapter: adapter() }
   };
   ```
4. Validar local que builda:
   ```bash
   pnpm install
   pnpm build
   ```
5. Asegurar `package.json` tiene `"start": "node build"` (adapter-node genera `build/index.js`):
   ```json
   "scripts": { "build": "vite build", "start": "node build", "dev": "vite dev" }
   ```
6. `.gitignore` debe excluir `node_modules`, `.svelte-kit`, `build`.
7. `github_push_workspace` y despues:
   ```
   coolify_create_app(repo_url=..., port=3000, build_pack="nixpacks")
   ```

### FastAPI / Python
1. Escribi `Dockerfile`:
   ```dockerfile
   FROM python:3.12-slim
   WORKDIR /app
   ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .
   EXPOSE 8000
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
2. Si usas `uv`:
   ```dockerfile
   FROM python:3.12-slim
   COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
   WORKDIR /app
   COPY pyproject.toml uv.lock ./
   RUN uv sync --frozen --no-install-project
   COPY . .
   RUN uv sync --frozen
   EXPOSE 8000
   CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
3. `.dockerignore` con `__pycache__`, `.venv`, `.env`, `data/`.
4. Validar local: `docker build -t test . && docker run -p 8000:8000 test`.
5. `coolify_create_app(repo_url=..., port=8000, build_pack="dockerfile")`.

### Rust (Actix / Axum)
1. Dockerfile multi-stage:
   ```dockerfile
   FROM rust:1-slim AS builder
   WORKDIR /app
   COPY . .
   RUN cargo build --release

   FROM debian:bookworm-slim
   RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
   WORKDIR /app
   COPY --from=builder /app/target/release/<binary-name> /app/server
   EXPOSE 8080
   CMD ["./server"]
   ```
2. Reemplaza `<binary-name>` por el `[package].name` del `Cargo.toml`.
3. Validar `cargo build --release` local (es lento, paciencia).
4. `coolify_create_app(repo_url=..., port=8080, build_pack="dockerfile")`.

### Go
1. Dockerfile multi-stage:
   ```dockerfile
   FROM golang:1.23-alpine AS builder
   WORKDIR /app
   COPY go.mod go.sum ./
   RUN go mod download
   COPY . .
   RUN CGO_ENABLED=0 go build -o /app/server ./...

   FROM alpine:latest
   RUN apk --no-cache add ca-certificates
   WORKDIR /app
   COPY --from=builder /app/server .
   EXPOSE 8080
   CMD ["./server"]
   ```
2. Idem rust pero mas rapido.

## Despues de `coolify_create_app`
1. Si necesitas env vars: `coolify_set_env(app_uuid=..., key=..., value=...)` por cada una. Marca `is_build_time=true` solo si el build necesita la var (raro para web apps).
2. `coolify_deploy(app_uuid)` para disparar el primer deploy.
3. Loop de status:
   ```
   coolify_status(app_uuid) -> si status="running" -> listo
                            -> si status="building"/"queued" -> shell sleep 15, reintentar
                            -> si status="failed"/"exited" -> leer payload, reportar al usuario
   ```
4. Cuando este `running`, reportar el `fqdn` al usuario (es el preview URL).

## Scaffolding non-interactivo

`pnpm create svelte` y `pnpm dlx sv create` son interactivos por default. Para evitar prompts:

**Opcion A — sv create con flags**:
```bash
pnpm dlx sv create . --template minimal --types ts --no-add-ons --install=pnpm
```

**Opcion B — escribir archivos a mano** con `write_file`. Mas determinista, mejor para apps chicas.

## Errores comunes y como tratarlos

| Sintoma | Causa probable | Fix |
|---|---|---|
| Coolify exit code != 0 en 30s | Sin server runnable (adapter-auto en svelte) | Cambiar a adapter-node + rebuild |
| Coolify queued >5min sin pasar a building | server uuid invalido o project uuid invalido | Validar envs del bot |
| Coolify build fail "no Dockerfile found" | Build pack mal | Si stack es Python/Rust/Go → `dockerfile`; si Node → `nixpacks` |
| Coolify deploy ok pero URL 502 | Puerto incorrecto | El `port` que pasaste a coolify_create_app debe ser el puerto que tu CMD/EXPOSE expone |
| Cert SSL fail | Cloudflare proxy on en wildcard | Pedirle al usuario que ponga gray cloud en el wildcard DNS |

## Resumen rapido (cheat sheet)
- Python/Rust/Go → escribi Dockerfile + `build_pack="dockerfile"` + puerto del CMD
- SvelteKit → adapter-node + `build_pack="nixpacks"` + port 3000
- Antes de `coolify_create_app`, **siempre** valida que builda local
- Despues, loopea `coolify_status` con sleeps hasta `running`
