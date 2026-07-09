---
name: reachability-audit
description: Auditoria de alcanzabilidad y navegacion. Cargala al construir o revisar cualquier app multi-pagina para garantizar que TODA ruta y TODA capacidad del backend tenga un punto de entrada VISIBLE en la UI. Mata los dead-ends — pantalla inicial en blanco, login inaccesible, acciones que fallan por falta de auth sin ofrecer camino al login, recursos compartibles (invites, servers, rooms) sin boton de copiar link/ID. Principio — toda URL debe ser alcanzable de alguna forma, salvo que sea privada o este limitada por permisos.
---

# Skill: Auditoria de Alcanzabilidad (Reachability)

## Principio central (no negociable)

**Toda ruta y toda capacidad debe ser alcanzable desde la UI mediante controles visibles — sin que el usuario tenga que tipear la URL a mano, leer la barra de direcciones, ni inspeccionar la base de datos.** La unica excepcion es una ruta privada o limitada por permisos; y "limitada por permisos" NO significa "invisible": significa que quien TIENE el permiso la alcanza, y a quien no lo tiene se le muestra un mensaje claro o un camino para obtenerlo.

Si construis una capacidad en el backend (crear server, unirse por ID, invitar, exportar, cambiar rol) y no hay un boton/link que la dispare, esa capacidad **no existe** para el usuario. Un backend perfecto detras de una UI inalcanzable es una app rota.

## Cuando usarla
- Cualquier app multi-pagina con auth, rutas, o recursos que se comparten.
- Al terminar de implementar y ANTES de dar por hecho: correr la auditoria de click-reachability.
- Cuando el usuario reporta "no encuentro donde...", "me quedo en blanco", "no me deja entrar", "tuve que copiar el ID de la URL".

## Cuando NO usarla
- Landing de una sola seccion sin rutas internas ni auth.
- APIs puras sin frontend.

## Los 4 dead-ends que estamos matando

Estos son fallos reales. Cada uno tiene una regla que lo previene.

### 1. Pantalla inicial en blanco / dead-end de entrada
`/` NUNCA puede renderizar vacio o un estado del que no se puede salir. Para un visitante **no autenticado**, `/` debe hacer UNA de estas dos:
- Renderizar una landing con CTAs visibles: **Iniciar sesion** y **Registrarse** (y una demo/preview si aplica), o
- Redirigir server-side a `/login`.

Nunca dejes `/` esperando datos que requieren sesion y mostrando en blanco cuando no hay. Todo estado terminal (lista vacia, error, sin permiso) ofrece una accion siguiente.

### 2. Login inaccesible
El acceso al login/registro debe estar SIEMPRE visible cuando no hay sesion:
- Boton "Iniciar sesion" en el nav/header en TODAS las paginas publicas.
- `/` no autenticado lleva a login en <=1 click.
- Nada de "primero tenes que llegar a una pantalla que a su vez linkea al login" — el login es de nivel 0.

### 3. Accion bloqueada por auth sin camino al login (el peor)
Cuando una accion falla por falta de autenticacion, **no alcanza con el error**. La UI debe ofrecer el camino:
- El guard server-side redirige a `/login?redirect=<ruta-actual>` en vez de tirar un 401 pelado.
- Si el gating es client-side, el mensaje "necesitas iniciar sesion" incluye un **link/boton a /login** ahi mismo.
- Tras loguear, volves a donde estabas (`redirect` param).

Un "no estas autenticado" sin boton para autenticarte es un callejon sin salida.

### 4. Recurso compartible sin afford­ance para compartir (el ID del server)
Si otros usuarios se unen/acceden a un recurso por un id o link (invite, server, room, board, doc, sala, evento), la UI DEBE exponer como obtener ese id/link. El usuario **nunca** debe tener que copiarlo de la barra de direcciones ni de la DB.
- Boton **Copiar link de invitacion** / **Copiar ID** bien visible en el recurso (header del server, menu, modal de "Invitar").
- Copia al portapapeles (`navigator.clipboard.writeText`) + confirmacion ("Copiado!") — con fallback si no hay clipboard API (input readonly + select).
- Idealmente: link de invitacion dedicado (`/invite/<code>`) ademas del ID crudo; opcional expiracion/revocacion.
- El flujo de "unirse" tambien tiene entrada visible: un boton **Unirse a un server** que pide el id/link.

```svelte
<!-- patron copiar-invite -->
<script lang="ts">
  let copied = $state(false);
  const invite = `${location.origin}/invite/${server.inviteCode}`;
  async function copy() {
    try { await navigator.clipboard.writeText(invite); }
    catch { /* fallback */ const i = document.createElement('input'); i.value = invite; document.body.append(i); i.select(); document.execCommand('copy'); i.remove(); }
    copied = true; setTimeout(() => copied = false, 1500);
  }
</script>
<button onclick={copy} aria-label="Copiar link de invitacion">
  {copied ? 'Copiado!' : 'Copiar invitacion'}
</button>
```

## Procedimiento — Matriz de alcanzabilidad

### Paso 1: listar TODAS las rutas y capacidades
Recorre `src/routes/**` (pages y `+server` endpoints) y las acciones/forms. Arma una fila por cada ruta navegable y cada capacidad (crear/unirse/invitar/editar/borrar/exportar/config/logout).

### Paso 2: llena la matriz. Toda fila DEBE tener una entrada visible.

| Ruta / Capacidad | Quien puede | Entrada visible (desde donde se llega) | Si no tiene permiso |
|------------------|-------------|----------------------------------------|---------------------|
| `/` (no auth) | todos | — (es la entrada) | render landing + CTA login/registro |
| `/login` | no auth | boton "Iniciar sesion" en header (todas las publicas) | ya logueado → redirect a app |
| `/app` (dashboard) | auth | redirect post-login + logo linkea aca | no auth → redirect a `/login?redirect=/app` |
| Crear server | auth | boton "+" en sidebar de servers | — |
| Unirse a server | auth | boton "Unirse" en sidebar → pide link/ID | — |
| Copiar invite | miembro | boton "Invitar/Copiar" en header del server | no miembro: no ve el server |
| `/settings` | auth | menu de usuario (avatar) → Configuracion | no auth → `/login?redirect=/settings` |
| Logout | auth | menu de usuario → Cerrar sesion | — |

**Cualquier fila cuya columna "Entrada visible" quede en "nada" o "solo tipeando la URL" es un BUG. Agregale el boton/link.**

### Paso 3: test de click-reachability (obligatorio)
Simula dos recorridos usando SOLO controles visibles (prohibido tipear URLs):
1. **Visitante no autenticado** desde `/`: ¿podes llegar a login y a registro? ¿`/` muestra algo accionable (no blanco)?
2. **Usuario autenticado** desde el dashboard: ¿podes alcanzar cada pantalla/capacidad clave (crear, unirse, invitar/copiar link, settings, logout)?

Si en agent-browser o a mano no llegas a una pantalla sin escribir la URL → falta la entrada. Agregala.

### Paso 4: consistencia de navegacion
- Nav/header presente y consistente en TODAS las paginas (no una pagina huerfana sin volver).
- Estado activo resaltado; el logo siempre linkea al home/dashboard.
- 404 (`+error.svelte`) con link a home — nunca un dead-end.
- Deep-link: recargar cualquier ruta valida funciona (no depende de estado en memoria de otra pagina).
- Back del browser predecible; tras login volves a `redirect`.

## Cross-check: capacidades del backend ↔ entradas en la UI
Por cada `+server.ts` / form action / mutacion que exista, confirma que hay al menos un control en la UI que lo dispara. Endpoints sin entrada = features fantasma. Entradas sin endpoint = botones muertos. Ambas son bugs.

## Checklist final
- [ ] `/` no autenticado no es blanco: landing con CTA o redirect a login
- [ ] Login/registro alcanzable en <=1 click desde cualquier pagina publica
- [ ] Guards redirigen a `/login?redirect=...`, no 401 pelado; mensajes de "sin sesion" linkean al login
- [ ] Tras login se vuelve a donde el usuario queria ir
- [ ] Todo recurso compartible tiene boton copiar-link/ID con confirmacion
- [ ] Flujo de "unirse" tiene entrada visible (no solo pegar URL)
- [ ] Matriz de rutas completa: cero filas sin entrada visible
- [ ] Test de click-reachability pasa para no-auth y para auth
- [ ] Cross-check backend↔UI: sin features fantasma ni botones muertos
- [ ] 404 y estados vacios/error ofrecen accion siguiente (nunca dead-end)

## Formato de salida

```
## Matriz de alcanzabilidad
| Ruta/Capacidad | Quien | Entrada visible | Sin permiso |
(una fila por ruta/capacidad — ninguna sin entrada)

## Dead-ends encontrados y arreglados
- {dead-end} → {entrada agregada / redirect agregado}

## Click-reachability
- No-auth desde `/`: [PASS/FAIL]
- Auth desde dashboard: [PASS/FAIL]

## Cross-check backend↔UI
- Endpoints sin entrada: {lista o "ninguno"}
- Botones sin endpoint: {lista o "ninguno"}
```

## Tools disponibles
read_file, write_file, list_dir, shell, load_skill, spawn_subagent (al sveltekit-expert para agregar las entradas faltantes).
