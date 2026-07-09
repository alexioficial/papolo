---
name: realtime-architecture
description: Patrones de comunicacion en tiempo real (SSE, WebSocket) vs request/response. Cargala cuando el dominio necesita que un usuario vea cambios de OTROS usuarios sin recargar — chat, mensajeria, notificaciones, presencia (quien esta en linea), feeds en vivo, dashboards live, colaboracion, multiplayer, subastas, indicador de escribiendo. Mata el anti-patron de setInterval/fetch en loop. Para SvelteKit adapter-node + Mongo.
---

# Skill: Arquitectura de Tiempo Real

## Cuando usarla
- El dominio tiene datos que **cambian por accion de OTROS usuarios** y el usuario actual los tiene que ver sin apretar F5: chat, DMs, comentarios en vivo, notificaciones push, "esta escribiendo...", presencia (online/offline), listas de miembros, feeds sociales, dashboards con metricas live, editores/pizarras/kanban colaborativos, multiplayer, subastas/pujas, trading, tracking en vivo.
- Estas por escribir un `setInterval(() => fetch(...), N)` para "refrescar" algo. **Pará.** Casi siempre es el sintoma de que necesitas esta skill.
- El planner marco el modelo de interaccion como "tiempo real".

## Cuando NO usarla
- Datos que solo cambian por accion del **propio** usuario (su carrito, su perfil, su lista de productos que solo el edita). Eso es CRUD normal: se re-lee al navegar o tras un submit.
- Reportes/analytics que se miran una vez y no necesitan estar vivos.

## Regla de oro (el error que estamos corrigiendo)

**NUNCA uses `setInterval`/`fetch` en loop para simular tiempo real.** Un chat que hace `fetch('/api/messages')` cada 2s esta roto por diseno:
- Latencia: los mensajes llegan hasta N segundos tarde.
- Costo: N peticiones por usuario por minuto aunque no pase nada — pega a la DB en vacio miles de veces.
- No escala: 100 usuarios en un canal = cientos de queries/segundo de puro ruido.
- Se ve amateur: el "salto" del refresco delata que no es real-time.

El tiempo real es **push** (el server avisa cuando hay algo), no **pull** (el cliente pregunta a lo bobo).

## Arbol de decision de transporte

Elegi el transporte MAS SIMPLE que cubra la direccion de datos que necesitas:

| Necesidad | Direccion | Transporte | Por que |
|-----------|-----------|-----------|---------|
| Notificaciones, feed en vivo, presencia, "escribiendo...", dashboard live, precios/subasta | server → cliente | **SSE** (Server-Sent Events) | Nativo en SvelteKit, cero deps, un solo deploy. El cliente manda cambios por POST normal. |
| Chat / mensajeria | ambas (pero cliente→server es esporadico) | **SSE + POST** (default) o WebSocket | SSE para recibir, POST para enviar. Cubre 95% de los chats sin custom server. |
| Multiplayer, cursores colaborativos, typing a alta frecuencia, juegos, señalizacion | ambas, alta frecuencia, baja latencia | **WebSocket** | Bidireccional real, menor overhead por mensaje. Requiere custom node server. |
| Audio/video/P2P | peer ↔ peer | **WebRTC** (señalizacion por WS) | Fuera de scope tipico; solo si lo piden explicito. |

**Default para Papolo (SvelteKit adapter-node, un solo deploy en Coolify): SSE + POST.** Es el patron correcto mas barato de operar. Subi a WebSocket solo si necesitas bidireccional de alta frecuencia y justificalo.

## Patron A — SSE (server → cliente). RECOMENDADO

Server→cliente puro, nativo en SvelteKit, sin custom server, sin dependencias.

### 1. Bus de eventos en proceso (`src/lib/server/bus.ts`)
Cuando un usuario escribe (POST), el server emite a un bus y todas las conexiones SSE abiertas de ese canal reciben. En un solo container esto alcanza y sobra.

```ts
import { EventEmitter } from 'node:events';
// Un emitter global por proceso. key = roomId, event = mensaje nuevo.
export const bus = new EventEmitter();
bus.setMaxListeners(0); // muchas conexiones SSE simultaneas
export function publish(roomId: string, data: unknown) {
  bus.emit(`room:${roomId}`, data);
}
```

### 2. Endpoint SSE (`src/routes/api/rooms/[id]/stream/+server.ts`)

```ts
import type { RequestHandler } from './$types';
import { bus } from '$lib/server/bus';

export const GET: RequestHandler = ({ params, locals, request }) => {
  if (!locals.user) return new Response('unauthorized', { status: 401 }); // auth server-side
  const roomId = params.id;
  const stream = new ReadableStream({
    start(controller) {
      const enc = new TextEncoder();
      const send = (d: unknown) => controller.enqueue(enc.encode(`data: ${JSON.stringify(d)}\n\n`));
      send({ type: 'ready' });
      const onMsg = (d: unknown) => send(d);
      bus.on(`room:${roomId}`, onMsg);
      // heartbeat: mantiene viva la conexion tras proxies (Coolify/Traefik matan idle)
      const hb = setInterval(() => controller.enqueue(enc.encode(': ping\n\n')), 25000);
      request.signal.addEventListener('abort', () => {
        clearInterval(hb);
        bus.off(`room:${roomId}`, onMsg); // CLEANUP obligatorio, sino leak
      });
    }
  });
  return new Response(stream, {
    headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' }
  });
};
```

### 3. Enviar = POST normal que persiste y publica

```ts
// src/routes/api/rooms/[id]/messages/+server.ts  (POST)
export const POST: RequestHandler = async ({ params, request, locals }) => {
  if (!locals.user) return new Response('unauthorized', { status: 401 });
  const { text } = await request.json();
  const msg = { _id: crypto.randomUUID(), roomId: params.id, userId: locals.user.id, text, at: Date.now() };
  await (await getDb()).collection('messages').insertOne(msg);
  publish(params.id, { type: 'message', ...msg }); // push a los que escuchan
  return json({ ok: true, msg });
};
```

### 4. Cliente (Svelte 5) — con reconexion

```svelte
<script lang="ts">
  let messages = $state<Msg[]>(data.initial); // pintado inicial via server load, NO fetch
  $effect(() => {
    const es = new EventSource(`/api/rooms/${roomId}/stream`);
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d.type === 'message') messages = [...messages, d];
    };
    // EventSource reconecta solo ante caida; onerror solo para logging
    return () => es.close(); // cleanup al desmontar
  });
  async function send(text: string) {
    await fetch(`/api/rooms/${roomId}/messages`, { method: 'POST', body: JSON.stringify({ text }) });
    // NO agregues el mensaje a mano aca: te llega por el stream (una sola fuente de verdad)
  }
</script>
```

La carga INICIAL de los mensajes va por `+page.server.ts` `load` (server-side, con cookie de sesion), NO por fetch client-side. El SSE solo trae lo NUEVO desde que abriste.

## Patron B — WebSocket (bidireccional). Solo si lo necesitas

Adapter-node no expone el server HTTP para el upgrade WS por defecto: necesitas un **custom server** que envuelva el handler del build.

```js
// server.js  → arranca con `node server.js` en vez de `node build` (ajusta el Dockerfile/CMD)
import { handler } from './build/handler.js';
import { createServer } from 'node:http';
import { WebSocketServer } from 'ws';

const server = createServer(handler);        // SvelteKit maneja el HTTP normal
const wss = new WebSocketServer({ server, path: '/ws' });
wss.on('connection', (ws, req) => {
  // AUTENTICA aca leyendo la cookie de sesion de req.headers.cookie — el upgrade no pasa por hooks
  ws.on('message', (buf) => { /* broadcast a la room */ });
  ws.on('close', () => { /* limpiar presencia */ });
});
server.listen(process.env.PORT || 3000);
```

Reglas WS: autentica en el `connection` (el upgrade NO pasa por `hooks.server.ts`), agrupa conexiones por room, mandale `ping` cada ~30s y cerra las que no responden `pong`, y limpia presencia en `close`. En dev, para tener WS con `vite dev`, usa un plugin con `configureServer` que attachee el mismo `WebSocketServer`.

## Polling honesto — cuando SI (la excepcion)

Polling es aceptable **solo** para estado de baja frecuencia donde el atraso no importa y no hay push disponible: ej. el estado de un build/deploy en un panel, o un job que tarda minutos. Reglas si lo usas:
- **Backoff**: empeza en 1-2s y agranda el intervalo si no hay cambios (2s → 4s → 8s, cap 15-30s).
- **Pausa cuando la pestaña esta oculta**: `document.visibilityState === 'hidden'` → no poolees.
- **Cleanup**: `clearInterval` al desmontar / al terminar. Nunca un loop infinito sin corte.
- **Corte por estado terminal**: cuando el job termina (done/failed), dejas de poolear.

Para chat, notificaciones, presencia o feeds NADA de esto aplica — eso es push (SSE/WS), no polling.

## Escalado / fan-out

- **1 solo container (caso Coolify default)**: el bus `EventEmitter` en proceso alcanza — el POST y el SSE viven en el mismo proceso.
- **Multiples instancias o writes desde afuera del proceso**: el bus en memoria no llega a las otras instancias. Opciones: **Mongo Change Streams** (`db.collection('messages').watch([{ $match: {...} }])` → publicas al bus local; requiere replica set / Atlas), o **Redis pub/sub** como bus compartido. Empeza con el bus en proceso y migra a change streams/Redis solo cuando escales horizontalmente.

## Estado real-time en el cliente

- **Una sola fuente de verdad**: el mensaje aparece cuando LLEGA por el stream, no cuando lo mandas. Evita duplicados (mande + me llega = 2). Si queres feedback instantaneo, hace optimistic UI con un `tempId` y reconcilia cuando el server confirma el id real.
- **Reconexion**: `EventSource` reconecta solo; para WS implementa reconexion con backoff exponencial + jitter y re-suscripcion a las rooms.
- **Gaps al reconectar**: al volver, pedi los mensajes desde `lastSeenId` por HTTP para no perder lo que paso mientras estabas desconectado.
- **Cleanup**: cerra el stream al desmontar el componente / cambiar de room (return del `$effect`).
- **Backpressure**: no acumules 10k mensajes en memoria; virtualiza o corta la lista.

## Checklist de tiempo real (antes de dar por hecho)

- [ ] Cero `setInterval`/`fetch`-loop para datos live (solo el excepcional de status con backoff+visibility+cleanup)
- [ ] Carga inicial por server `load`, no por fetch client-side
- [ ] SSE/WS autenticado server-side (chequea `locals.user` / la cookie)
- [ ] Heartbeat/ping para no morir tras el proxy (~25-30s)
- [ ] Cleanup de listeners y del stream al desmontar / abort (sin leaks)
- [ ] Una sola fuente de verdad (sin duplicar el propio mensaje)
- [ ] Reconexion + recuperacion de gap (desde lastSeenId)
- [ ] Fan-out correcto para la topologia (bus en proceso 1 instancia; change streams/Redis si escalas)

## Formato de salida

```
## Modelo de interaccion
- Real-time: {que datos son push y por que}
- Transporte elegido: SSE | SSE+POST | WebSocket — porque {razon}

## Implementacion
- Bus/pub-sub: {archivo}
- Endpoint stream: {ruta}
- Cliente: {componente}
- Fan-out: {en proceso | change streams | redis}

## Checklist real-time
- [PASS/FAIL] sin polling loops
- [PASS/FAIL] auth en el stream
- [PASS/FAIL] cleanup/heartbeat
- [PASS/FAIL] reconexion + gap recovery
```

## Tools disponibles
read_file, write_file, list_dir, shell, load_skill, spawn_subagent (al sveltekit-expert para implementar siguiendo este patron).
