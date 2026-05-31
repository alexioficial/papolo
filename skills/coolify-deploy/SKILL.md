---
name: coolify-deploy
description: Como deployar un proyecto a Coolify. REGLA UNICA: siempre Dockerfile, NUNCA nixpacks ni docker-compose. Incluye templates Dockerfile por stack (SvelteKit, Python, Rust, Go, static). Cargala antes de llamar coolify_create_app.
---

# Skill: coolify-deploy

## REGLA NRO 1 (no negociable)
**Siempre `build_pack="dockerfile"`.** Nunca nixpacks. Nunca docker-compose. Sin excepciones, incluso para Node/SvelteKit.

Razon: nixpacks adivina el start command y a veces le erra; docker-compose en Coolify trae problemas conocidos. Dockerfile escrito a mano es 100% deterministico.

## Cuando usarla
- Vas a llamar `coolify_create_app` por primera vez
- El usuario pide "deployalo", "subilo a coolify", "haceme un preview", etc

## Procedimiento general
1. Identifica el stack del proyecto.
2. **Escribi `Dockerfile`** en el workspace usando el template correspondiente abajo.
3. **Escribi `.dockerignore`** para no copiar basura.
4. **Validar** que el build funciona localmente (`docker build` si tenes docker disponible — sino al menos `pnpm build` / `cargo build --release` / etc).
5. `github_create_repo` + `github_push_workspace`.
6. `coolify_create_app(repo_url=..., port=<puerto del CMD>, build_pack="dockerfile")`.
7. Si necesitas env vars: `coolify_set_env` antes del primer deploy.
8. `coolify_deploy(app_uuid)`.
9. **Loop de status** (ver mas abajo) hasta que sea `running` o `failed`.
10. Si `running`: REPORTAR EL URL al usuario y PARAR.

## Templates Dockerfile

### SvelteKit / Node / Vite SSR
**Requiere** `@sveltejs/adapter-node` (no adapter-auto). Pasos antes del Dockerfile:
```bash
pnpm add -D @sveltejs/adapter-node
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
Asegurar `package.json` tenga `"start": "node build"`.

**Dockerfile** (puerto 3000):
```dockerfile
FROM node:20-slim AS deps
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; \
    else pnpm install --no-frozen-lockfile; fi

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
Puerto 8000:
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
Multi-stage para imagen final chica. Reemplaza `<binary>` por el `[package].name` de `Cargo.toml`:
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

### Static (HTML + JS, sin backend)
Sirve con nginx alpine, puerto 80:
```dockerfile
FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80
```
Si tenes build step (Vite, etc):
```dockerfile
FROM node:20-slim AS builder
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

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
| `queued` | Esperando worker | **Sigue esperando**. Reintenta en 15s. |
| `building` | Buildeando imagen | **Sigue esperando**. Reintenta en 15s. |
| `starting` | Imagen lista, container arrancando | **Sigue esperando**. Reintenta en 15s. |
| `running:healthy` / `running:unknown` | **EXITO** | **PARA. Reporta el URL al usuario. NO destruyas ni rehagas nada.** |
| `failed` / `exited` | Falla real | Lee el payload, identifica el error, fixea, `coolify_deploy` denuevo. NO recrees la app entera. |

**Importante:** `running:unknown` significa que arrancó pero no hay healthcheck configurado. Para web apps simples eso es **exito**. No te dejes confundir por el "unknown".

**Limite de espera:** maximo 6-8 minutos (24-32 polls de 15s). Si pasa eso sin alcanzar `running`, asumi falla y reporta al usuario con el ultimo payload de status.

## Cuando NO destruir

`coolify_destroy_app` es para casos extremos. NO la uses solo porque:
- Un deploy falló (mejor `coolify_deploy` denuevo despues de fixear)
- Quieres cambiar el Dockerfile (push nuevo commit y `coolify_deploy`, no necesita destruir)
- El status es ambiguo

Solo destruis si el usuario lo pide explicitamente, o si el proyecto cambio tanto de stack que la app necesita rearmarse desde cero (ej: pasaste de webserver a worker).

## Errores comunes y como leerlos

| Sintoma | Causa probable | Fix |
|---|---|---|
| Status pasa a `failed` en <30s | Build error: dependencia faltante, syntaxis | Lee el payload, fixea, `coolify_deploy` |
| Status queda en `building` >5 min | Build lento o stuck (rust, big node_modules) | Esperar mas, hasta 8 min |
| `running` pero el URL devuelve 502 | Puerto del CMD != `port` que pasaste a `coolify_create_app` | `coolify_set_env` + redeploy, o recrear con el puerto correcto |
| `running` pero URL devuelve "no such service" | DNS aun propagandose (raro con wildcard) | Esperar 30s, recargar |

## Cheat sheet

1. Dockerfile siempre. Nunca nixpacks. Nunca docker-compose.
2. SvelteKit → adapter-node + el Dockerfile de arriba + port 3000.
3. Python → Dockerfile + port 8000.
4. Rust/Go → Dockerfile multistage + port 8080 (o el que use tu app).
5. Static → nginx alpine + port 80.
6. Despues de `coolify_deploy`: loop con `sleep 15` hasta `running:*`.
7. Cuando llegue a `running`: REPORTAR EL URL y PARAR. No rehagas nada.
