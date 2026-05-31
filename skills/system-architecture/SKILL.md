---
name: system-architecture
description: Diseno arquitectonico profesional de sistemas. Cargala para disenar la arquitectura de cualquier sistema/app/proyecto antes de escribir codigo. Produce un ARCH.md completo con componentes, data flow, decisiones y tradeoffs. Complementa al subagent planner con profundidad tecnica.
---

# Skill: Diseno de Arquitectura de Sistemas

## Cuando usarla
- El usuario pide "un sistema", "una app", "una plataforma"
- Despues del planner, cuando toca disenar la arquitectura concreta
- Cuando hay decisiones de arquitectura no triviales (mono vs micro, SPA vs SSR, DB relacional vs documental)
- Antes de llamar a cualquier subagente de implementacion

## Cuando NO usarla
- Bugs simples, cambios cosmeticos, typo fixes
- Cuando el sistema ya tiene arquitectura definida y solo se agrega una feature pequeña

## Procedimiento

### Fase 0: Lectura del Plan del Planner

Si el planner ya fue invocado, lee su output. Si no, invocalo primero via `spawn_subagent(planner)`. El plan del planner tiene las features explicitas e implicitas. Tu trabajo es traducir ese plan a arquitectura concreta.

### Fase 1: ARCH.md — Documento de Arquitectura (OBLIGATORIO)

Crea `ARCH.md` en la raiz del proyecto antes de escribir codigo de produccion.

#### 1. Resumen Ejecutivo
2-3 lineas: que hace el sistema, stack elegido, por que.

#### 2. Stack Tecnologico (decisiones concretas)
| Capa | Tecnologia | Justificacion |
|------|-----------|---------------|
| Frontend | SvelteKit + adapter-node | SSR, server routes, TypeScript |
| Estilos | Tailwind 4 | Utilidades, diseno systema en CSS |
| Backend / API | SvelteKit server routes (full-stack) O FastAPI separado | Ver regla arquitectura abajo |
| DB | MongoDB (cluster compartido) | Documental, flexible, ya existe |
| Auth | JWT + bcrypt + cookies httpOnly | Stateless, SvelteKit handle hook |
| Deploy | Coolify + Dockerfile | Deterministico, siempre dockerfile |

**Regla de Arquitectura Web (NO NEGOCIABLE):**
- Opcion A (default): SvelteKit full-stack con adapter-node. Server routes conectan directo a Mongo. Un solo deploy puerto 3000.
- Opcion B (solo si se justifica backend separado): SvelteKit adapter-node (frontend, puerto 3000) + backend separado (FastAPI/Actix, puerto 8000/8080). DOS deploys, DOS URLs. NUNCA bundlear SvelteKit en otro backend.

Elegi A por defecto. Elegi B solo si: necesitas Python/Rust para algo especifico, o el usuario pide backends separados explicitamente.

#### 3. Modelo de Datos
Para cada entidad del dominio:
- Collection/table name
- Schema (campos, tipos, defaults)
- Indexes necesarios (compound, unique, TTL)
- Relaciones (embedded vs referenced)

```typescript
// Ejemplo:
interface User {
  _id: ObjectId;
  email: string;          // unique index
  passwordHash: string;
  role: 'admin' | 'user'; // index
  name: string;
  createdAt: Date;         // default: now
  updatedAt: Date;
}
```

#### 4. Rutas API / Server Routes
Para cada ruta:
```
GET  /api/products        → list (paginated, search, filter)
GET  /api/products/[id]   → detail
POST /api/products        → create (admin only)
PATCH /api/products/[id]  → update (admin only)
DELETE /api/products/[id] → delete (admin only, soft)
```

Proteccion por rol especificada en cada ruta.

#### 5. Autenticacion y roles
- Estrategia: JWT en cookie httpOnly + SvelteKit hooks.handle
- O auth providers si aplica
- Roles definidos con sus permisos exactos
- Proteccion server-side (NO confiar solo en client-side)

#### 6. Flujo de datos
Por cada feature principal, describe:
1. User action
2. Request flow (component → load function / form action → server → DB → response)
3. Error handling en cada paso
4. Edge cases

#### 7. Decisiones y Tradeoffs
Para cada decision no obvia:
- Opcion A vs Opcion B
- Por que elegiste A
- Que sacrificas (tradeoff honesto)

#### 8. Riesgos y Mitigaciones
- DB connection lazy (nunca eager al boot)
- Rate limiting en endpoints publicos
- Validacion server-side (nunca confiar en client-side sola)
- Cache busting en Dockerfile para evitar stale content

### Fase 2: Features Implicitas (Checklist Obligatorio)

NO asumas que el usuario las pidio. Evaluar cada una y documentar en ARCH.md:

- [ ] **Auth/login**: si maneja datos privados o usuarios, SIEMPRE. Email+password + bcrypt + JWT.
- [ ] **Roles/permisos**: admin/user/viewer. Proteger rutas server-side.
- [ ] **Validacion server-side**: campos requeridos, formatos (email, SKU), rangos (precio >= 0), unicidad.
- [ ] **Manejo de errores**: HTTPException con mensajes claros, errores estructurados por campo en forms.
- [ ] **Estados vacios**: "No hay productos" con CTA para crear primero.
- [ ] **Paginacion**: listas > 20 items. Default 20, max 100.
- [ ] **Busqueda/filtros**: search basico por texto en colecciones principales.
- [ ] **Auditoria**: created_at, updated_at, created_by en cada entidad.
- [ ] **Seed data**: script que crea admin inicial + 2-3 records de prueba.
- [ ] **Edge cases del dominio**: producto sin stock, usuario sin email, duplicados, cancelaciones.

### Fase 3: Plan de Implementacion (pasos concretos)

Despues del ARCH.md, genera un plan de implementacion con pasos ordenados:

1. Scaffold del proyecto (SvelteKit init, Tailwind, dependencias, Dockerfile)
2. DB connection (lazy pattern, env vars, primeros indexes)
3. Auth system (register, login, logout, middleware, seed admin)
4. Modelos + CRUD base (con validacion)
5. UI scaffolding (layout, navigation, error pages)
6. Features por orden de dependencia (cada una: server route + componente + tests)
7. Seed data
8. Deploy (repo, push, Coolify create, env vars, deploy)

Cada paso indica:
- **Archivos a tocar**
- **Riesgo**: bajo/medio/alto
- **Validacion**: como saber que funciona
- **Delegar a**: que subagente ejecuta

### Fase 4: Reglas de Codigo (pasar a los subagentes)

Al delegar a subagentes, incluir estas reglas en el task:

1. **DB lazy siempre** — `get_db()` on-demand, nunca connect al boot. Si falla, return error, no crash.
2. **Validacion dual** — client-side (UX) + server-side (seguridad). Nunca confiar solo en client.
3. **Errores estructurados** — todos los endpoints devuelven `{ ok: boolean, data?, error?: { message, fields? } }`
4. **Paginacion** — todas las listas. Query params: `?page=1&limit=20`. Response: `{ items, total, page, totalPages }`.
5. **Auditoria** — toda entidad tiene `created_at`, `updated_at`, `created_by` si aplica.
6. **No secrets en codigo** — env vars siempre. `MONGODB_URI` via env.

## Formato de salida
```
## ARCH.md (link al archivo)
## Resumen de decisiones
- Stack: ...
- Arquitectura: full-stack / separado
- Auth: ...
- DB: ...

## Plan de implementacion
1. {paso} → archivos: {a, b} → delegar a: {subagent}

## Riesgos principales
- {riesgo} → mitigacion: {como}
```

## Tools disponibles
read_file, write_file, list_dir, shell (para inspeccion), load_skill, spawn_subagent (al planner, sveltekit-expert, fastapi-expert, mongodb-expert)
