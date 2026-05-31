---
name: coolify-deploy
description: Como deployar un proyecto a Coolify — siempre Dockerfile, nunca nixpacks ni docker-compose. Templates por stack (SvelteKit, Python, Rust, Go, static). Cargala antes de llamar coolify_create_app.
---

# Skill — coolify-deploy

## REGLA NRO 1 (no negociable)
**Siempre `build_pack="dockerfile"`.** Nunca nixpacks. Nunca docker-compose. Sin excepciones, incluso para Node/SvelteKit.

Razon — nixpacks adivina el start command y a veces le erra; docker-compose en Coolify trae problemas conocidos. Dockerfile escrito a mano es 100% deterministico.

## Cuando usar esta skill
- Vas a llamar `coolify_create_app` por primera vez.
- El usuario pide "deployalo", "subilo a coolify", "haceme un preview", etc.

## Procedimiento general
1. Identifica el stack del proyecto.
2. Detecta el package manager mirando lockfiles (ver "Package manager" abajo).
3. **Escribi `Dockerfile`** en el workspace usando el template correspondiente.
4. **Escribi `.dockerignore`** para no copiar basura.
5. Validar que builda local — segun stack — `pnpm build` / `npm run build` / `cargo build --release` / etc.
6. `github_create_repo` + `github_push_workspace`.
7. `coolify_create_app(repo_url=..., port=<puerto del CMD>, build_pack="dockerfile")`.
8. Si necesitas env vars — `coolify_set_env` o `coolify_set_mongodb_env` ANTES del primer deploy.
9. `coolify_deploy(app_uuid)`.
10. **Loop de status** (ver abajo) hasta `running` o `failed`.
11. Si `running` — REPORTA EL URL al usuario y PARA. No reescribas, no destruyas, no rehagas.

## Package manager — detectar antes de escribir Dockerfile

Mira los lockfiles del workspace:

| Lockfile presente | Package manager | Comando install | Comando build |
|---|---|---|---|
| `pnpm-lock.yaml` | pnpm | `pnpm install --frozen-lockfile` | `pnpm build` |
| `package-lock.json` | npm | `npm ci` | `npm run build` |
| `yarn.lock` | yarn | `yarn install --frozen-lockfile` | `yarn build` |
| ninguno + package.json | npm | `npm install` y crear lockfile | `npm run build` |

**No mezcles** — si el lockfile es de npm pero el Dockerfile usa `pnpm`, el deploy falla con "pnpm not found" o lockfile mismatch. Mira `package.json` field `packageManager` tambien si esta seteado.

## Templates Dockerfile

### SvelteKit / Node SSR (npm)
Aplica cuando hay `package-lock.json`. Puerto 3000.

**SvelteKit requiere** `@sveltejs/adapter-node` (no adapter-auto, no adapter-static — siempre adapter-node aunque la app sea solo cliente). Pasos antes del Dockerfile:
```bash
npm install -D @sveltejs/adapter-node
```
Sobrescribir `svelte.config.js`:
```js
import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
export default {
  preprocess: vitePreprocess(),
  kit: { adapter: adapter() }
};
```

```dockerfile
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", "build"]
```

### SvelteKit / Node SSR (pnpm)
Aplica cuando hay `pnpm-lock.yaml`. Puerto 3000.

```dockerfile
FROM node:20-slim AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:20-slim AS builder
WORKDIR /app
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
EXPOSE 3000
CMD ["node", "build"]
```

### Python / FastAPI con uv
Puerto 8000.
```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_SYSTEM_PYTHON=1
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project 2>/dev/null || uv pip install --system -e .
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Python / FastAPI con pip
Puerto 8000.
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

### Rust (Actix / Axum)
Reemplaza `<binary>` por el `[package].name` de `Cargo.toml`. Puerto 8080.
```dockerfile
FROM rust:1-slim AS builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/target/release/<binary> /app/server
EXPOSE 8080
CMD ["./server"]
```

### Go
Puerto 8080.
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

### Static (HTML + JS puro, NO SvelteKit)
Solo para proyectos sin framework (HTML + JS plain, Vite vanilla, etc). **NO uses esto para SvelteKit** — SvelteKit va siempre con adapter-node arriba. Puerto 80.

```dockerfile
FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
```

Con build step (Vite, etc):
```dockerfile
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
```

## .dockerignore (siempre incluir)
```
.git
.github
node_modules
.svelte-kit
build
dist
target
.venv
__pycache__
*.pyc
.env
.env.*
data/
.DS_Store
```

## Polling de status (critico)

Despues de `coolify_deploy`, llama `coolify_status` en loop con `shell sleep 15` entre cada call. Estados:

| status | Significa | Que haces |
|---|---|---|
| `queued` | Esperando worker | Sigue esperando. Reintenta en 15s. |
| `building` | Buildeando imagen | Sigue esperando. Reintenta en 15s. |
| `starting` | Imagen lista, container arrancando | Sigue esperando. Reintenta en 15s. |
| `running:healthy` / `running:unknown` | **EXITO** — PARA, reporta el URL, no destruyas ni rehagas. |
| `failed` / `exited` | Falla real | Lee el payload, identifica el error, fixea, `coolify_deploy` denuevo. NO recrees la app entera. |

**Importante** — `running:unknown` significa que arrancó pero no hay healthcheck configurado. Para web apps simples eso es **exito**. No te dejes confundir por el "unknown".

**Limite de espera** — maximo 6-8 minutos (24-32 polls de 15s). Si pasa eso sin alcanzar `running`, asumi falla y reporta al usuario con el ultimo payload.

## Cambiar puerto, branch, o buildpack despues de crear la app
**NO destruyas y recrees.** Usa `coolify_update_app(app_uuid, port=...)` (o `branch=`, `build_pack=`) y despues `coolify_deploy`.

## Cuando NO destruir
`coolify_destroy_app` es para casos extremos. NO la uses solo porque:
- Un deploy falló — mejor `coolify_deploy` denuevo despues de fixear.
- Querés cambiar el Dockerfile — push nuevo commit y `coolify_deploy`.
- El status es ambiguo.
- Querés cambiar el puerto — usa `coolify_update_app`.

Solo destruis si el usuario lo pide explicitamente, o si el proyecto cambio tanto de stack que la app necesita rearmarse desde cero.

## Env vars (Coolify)

`coolify_set_env(app_uuid, key, value)` y `coolify_set_mongodb_env(app_uuid)` setean **runtime** vars (no build-time). El endpoint hace upsert — si la key ya existe, la actualiza. Despues SIEMPRE llama `coolify_deploy` para que el container las tome.

Si una tool te devolvio error 422 o similar, NO la reintentes con los mismos args. Cambiá el approach.

## Errores comunes

| Sintoma | Causa probable | Fix |
|---|---|---|
| `failed` en <30s | Build error — dependencia faltante, sintaxis, lockfile mismatch | Lee el log/payload, fixea, `coolify_deploy`. Mira que el Dockerfile use el package manager correcto. |
| `building` >5 min | Build lento (rust, big node_modules) | Esperar mas, hasta 8 min |
| `running` pero el URL devuelve 502 | Puerto del CMD != `ports_exposes` de la app | `coolify_update_app(app_uuid, port=<correcto>)` + `coolify_deploy` |
| `running` pero el URL devuelve "no such service" | DNS aun propagandose (raro con wildcard) | Esperar 30s, recargar |
| `exited:unhealthy` | El container crashea al startup — falta env var critica, conexion eager a DB rota | Asegurate que las envs esten seteadas y el codigo conecte de forma **lazy** (no en el module-load) |

## Cheat sheet
1. Dockerfile siempre. Nunca nixpacks. Nunca docker-compose.
2. SvelteKit → adapter-node + Dockerfile node + port 3000. Siempre. Aunque sea solo cliente.
3. Python → Dockerfile + port 8000.
4. Rust / Go → Dockerfile multistage + port 8080.
5. Static (no SvelteKit) → nginx alpine + port 80.
6. Despues de `coolify_deploy` — loop con `sleep 15` hasta `running:*`.
7. Cuando llegue a `running` — REPORTA EL URL y PARA. No rehagas nada.
8. Para cambiar puerto/branch despues de crear — `coolify_update_app`, no destruir.
9. Despues de `coolify_set_env` siempre `coolify_deploy`.
