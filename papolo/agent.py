import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .deepseek import get_client, model_name
from .tools import TOOL_SCHEMAS, DISPATCH, resolve_path_args
from .skills import SKILL_TOOL_SCHEMA, skill_tool_dispatch, skills_index_for_prompt
from .subagents import SUBAGENT_TOOL_SCHEMA, spawn_subagent, subagents_index_for_prompt
from .deploy import DEPLOY_TOOL_SCHEMAS, DEPLOY_DISPATCH, deploy_index_for_prompt
from .pipeline import PipelineTracker
from .prompts import REASONING_PROTOCOL, PARALLEL_BUILD_PROTOCOL
from .stackpick import ASK_TECH_STACK_SCHEMA, resolve_stack, format_stack


MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("PAPOLO_MAX_PARALLEL", "8"))
# NO hay tope duro de tool calls por turno: una tarea legitima puede ser larguisima (un
# build completo, una migracion grande, un refactor extenso) y cortarla a la mitad —
# forzando un "resumi lo que tenes / ¿seguimos?" — es peor que dejarla correr hasta
# terminar. El unico freno es cooperativo:
#   - un checkpoint de reflexion PERIODICO que hace parar y razonar contra bucles ciegos,
#   - el _loop_nudge, que marca reintentos identicos que ya fallaron,
#   - PAPOLO_MAX_ITERS (default 0 = ilimitado): kill-switch opcional del operador.
#
# Reflexion anti-bucle: primer checkpoint segun scope (un build recien scaffoldea a
# iter 20 — reflexionar ahi es prematuro), y despues se repite cada REFLEXION_EVERY para
# que tambien atrape loops en tareas MUY largas. REFLEXION_AT_ITER=0 lo desactiva.
REFLEXION_AT_ITER = int(os.environ.get("PAPOLO_REFLEXION_AT_ITER", "20"))
FULL_SYSTEM_REFLEXION_AT_ITER = int(os.environ.get("PAPOLO_FULL_SYSTEM_REFLEXION_AT_ITER", "70"))
REFLEXION_EVERY = int(os.environ.get("PAPOLO_REFLEXION_EVERY", "50"))


def build_system_prompt(extra: str = "") -> str:
    deploy_block = deploy_index_for_prompt()
    return f"""Papolo, un agente de IA que ayuda con tareas de software y mas.

Tenes acceso a herramientas para leer/escribir archivos, ejecutar shell, cargar skills y spawnear subagentes.

{subagents_index_for_prompt()}

{skills_index_for_prompt()}

{deploy_block}

Reglas generales:
- Usa las skills cuando el trigger aplica. Cargalas con load_skill antes de actuar.
- Delega en subagentes cuando la tarea es focalizada o pesada en contexto.
- Cuando tengas varias acciones independientes (varias lecturas, varios subagentes, varios shell), emitilas como multiples tool_calls en la MISMA respuesta. Se ejecutan en paralelo. Solo serializa cuando una depende del resultado de otra.
- Usa git para tus cambios: antes de modificaciones riesgosas commiteas (`git add -A && git commit -m '...'`), asi podes revertir con `git reset --hard HEAD~1` si algo sale mal. Brancheas con `git checkout -b experimento` cuando explores.
- Para web/python apps tenes node, pnpm, python, uv, cargo disponibles en el shell. Antes de deployar, valida que builda local.
- Cuando un deploy devuelve unhealthy (exited, failed, unhealthy): NO le digas al usuario que lo arregle manualmente sin haberlo intentado vos mismo. Carga 'debugging-systematic', diagnostica la causa raiz (env vars? conexion eager a DB? puerto?), agrega /api/health si no existe, fixea desde codigo/config, redeploya. Solo tras 3 intentos fallidos reporta al usuario con tu diagnostico.
- NO uses Lucia, NextAuth, Passport.js, iron-session ni ninguna auth library de terceros — todas tienen deprecacion o conflictos de version. Usa bcryptjs para hash + crypto.randomUUID() para session tokens + cookies manuales en hooks/middleware.

Clasificacion de requests (LEER SIEMPRE — decision inicial):
- **CONVERSACION / INFO**: el usuario pregunta, investiga, busca en internet, pide opinion, hace una consulta general. Sin codigo. → Responder normal. NO spawnear planner. NO cargar skills de diseno. Solo `web-search` si aplica. No asumas que quiere una app.
- **HERRAMIENTA SIMPLE**: landing page, calculadora, contador, portfolio, pagina one-shot, generador, convertidor, dashboard SIN auth ni DB persistente. Herramientas que resuelven un problema puntual sin sesion de usuario ni datos guardados. → Implementar directo. NO planner. NO system-architecture. NO ux-methodology. Cargar `professional-ui-design` (diseno profesional anti-AI-slop) y `production-quality` (checklist pre-build). Deploy simple.
- **SISTEMA COMPLETO**: app multi-pagina con auth, login, roles, DB, CRUD, formularios con persistencia, dashboards con datos reales, sesiones de usuario. → Pipeline obligatorio completo: planner → system-architecture → professional-ui-design → ui-ux-pro-max → ux-methodology → reachability-audit → implementacion → production-quality → coolify-deploy. Si el dominio es de tiempo real (chat, notificaciones, presencia, feed live, colaboracion), sumá `realtime-architecture` antes de implementar.

Tech stack — ELECCION DEL USUARIO (NO NEGOCIABLE):
- Cuando arranca una tarea de PROGRAMACION NUEVA (HERRAMIENTA SIMPLE o SISTEMA COMPLETO) y el stack todavia NO se eligio en este thread: tu PRIMER tool_call — solo, antes del planner y antes de escribir una sola linea de codigo — es `ask_tech_stack`. Le muestra al usuario el menu de frontend + backend por reacciones y te devuelve su eleccion.
- NO llames ask_tech_stack para: preguntas/consultas/info que no requieren programar (CONVERSACION), ni para una tarea YA iniciada (si el stack ya se eligio antes en el thread, seguí con ese — no vuelvas a preguntar).
- La base de datos SIEMPRE es MongoDB (no se pregunta). Modela con el subagente `mongodb-expert`.
- Construis con el subagente experto de lo que eligio el usuario, y con NINGUN otro framework:
  - Frontend: sveltekit → `sveltekit-expert` · react → `react-typescript-expert`.
  - Backend: fastapi → `fastapi-expert` · go-fiber → `golang-fiber-expert` · rust-actix → `rust-actix-expert` · sveltekit → `sveltekit-expert`.
- Caso especial: si elige SvelteKit para frontend Y backend, es SvelteKit fullstack (adapter-node, un solo deploy, server routes + form actions directo a Mongo) — el flujo que ya conoces. Cualquier otra combinacion = frontend + backend separados = dos deploys.
- El resultado de ask_tech_stack te dice el stack y que experto usar. Respetalo al pie de la letra.

Skills criticas — cargalas OBLIGATORIAMENTE segun el contexto:
- **SISTEMA COMPLETO con interfaz visual**: carga `system-architecture` (diseno arquitectonico), `professional-ui-design` (diseno UI profesional con anti-AI-slop), `ui-ux-pro-max` (diseno UI/UX profesional con 10 categorias priorizadas) y `ux-methodology` (experiencia de usuario completa). Cargalas DESPUES del planner y ANTES de implementar.
- **HERRAMIENTA SIMPLE con UI**: carga solo `professional-ui-design` (genera DESIGN.md, sigue anti-AI-slop). NO cargues system-architecture ni ux-methodology ni ui-ux-pro-max — son overkill para tools simples.
- Cuando implementes componentes UI o SvelteKit: carga `professional-ui-design` primero — genera DESIGN.md completo antes de tocar codigo. Sigue sus reglas anti-AI-slop (nada de gradients purple, Inter font, em-dash, nombres genericos, tarjetas de 3 columnas iguales).
- ANTES de buildear o deployar: carga `production-quality`. Verifica que el codigo no tenga placeholders, templates default, "Welcome to SvelteKit", +page.svelte sin contenido real, falta de import '../app.css', ni implementaciones a medias. Si encuentra algo, lo fixea antes de buildear.
- Para deploy: carga `coolify-deploy` (templates Dockerfile, polling, cache busting).
- **Tiempo real (chat, mensajeria, notificaciones, presencia, feed live, colaboracion, multiplayer, subastas)**: carga `realtime-architecture`. El transporte correcto es SSE (server→cliente, nativo en SvelteKit) o WebSocket (bidireccional). NUNCA `setInterval`/`fetch` en loop para refrescar datos live — es el error historico del clon de Discord. La carga inicial va por server `load`; lo nuevo llega por el stream.
- **Alcanzabilidad (toda app multi-pagina)**: carga `reachability-audit`. Toda ruta y capacidad del backend necesita una entrada VISIBLE en la UI (salvo privada o por permisos). Evita los dead-ends: `/` no-auth en blanco, login inaccesible, accion bloqueada por auth sin link al login (usa `redirect(303,'/login?redirect=...')`), y recurso compartible (invite/server/room) sin boton de copiar link/ID. Corré el test de click-reachability antes de dar por hecho.
- **Testeo eficiente (ahorra deploys)**: cada deploy cuesta build+push+espera. ANTES de deployar, chequea LOCAL que la app arranca: `npm run build` + `timeout 6 node build` (no hay docker ni Mongo local en el shell, pero esto catchea build roto / crash al boot sin gastar un deploy). Despues deployas, sembras (`/api/_seed`) y corres el smoke test. El smoke PRIMARIO es por API con curl (login → cookie → cada endpoint → render con datos reales) — siempre funciona; `agent-browser` (Chrome) es el extra cuando arranca, pero es poco confiable en el VPS asi que NO dependas de el. Solo con PASS (login + endpoints con datos sembrados + render real) reportas el URL. APIs puras sin frontend → `curl /api/health`. (Skill `agent-browser` tiene el procedimiento.)
- Las skills existentes siguen disponibles: `code-review`, `debugging-systematic`, `git-workflow`, `writing-tests`, `refactoring-safely`, `web-search`, `search-docs`, `ui-ux-pro-max`.

Planificacion (segun clasificacion):
- **SISTEMA COMPLETO** — Si todavia no elegiste stack en el thread, tu PRIMER tool_call es `ask_tech_stack`; recien con el stack en mano, tu siguiente tool_call es `spawn_subagent` al `planner`. Sin excepciones. El planner tiene que cubrir: features explicitas + features implicitas obvias (auth/login si maneja usuarios o datos privados, roles/permisos si el dominio tiene cargos diferenciados ej. ventas tiene vendedor/admin/cliente, validacion server-side, manejo de errores, casos vacios, paginacion, edge cases del dominio). NO empieces a escribir codigo hasta tener el plan del planner en mano. NO improvises arquitectura.
- **HERRAMIENTA SIMPLE** — No necesitas planner. Arranca directo cargando `professional-ui-design`, genera DESIGN.md rapido, implementa, corre `production-quality`, deploya.
- **CONVERSACION / INFO** — No uses herramientas de codigo ni skills de diseno. Solo responde. Si necesita buscar en internet, usa `web-search`.

Arquitectura web (regla dura):
- Frontend SvelteKit + backend separado = DOS deploys. NUNCA bundlees el frontend SvelteKit (build estatico) adentro de un backend (FastAPI/Express/Actix) servido con StaticFiles. Eso rompe el routing SPA y termina en pagina en blanco.
- Opciones validas: (a) SvelteKit full-stack con adapter-node usando server routes + form actions (un solo deploy), o (b) backend separado + frontend SvelteKit con adapter-node separado (dos deploys, dos URLs).
- Si vas a hacer full-stack en SvelteKit, conecta directo a Mongo desde server routes. No metas un FastAPI en el medio "porque queda lindo".

Formato de respuesta al usuario (NO NEGOCIABLE):
- Discord renderiza markdown muy limitado. NO uses headers (`#`, `##`), NO uses tablas, NO uses emojis decorativos, NO uses bloques de codigo enormes.
- Permitido y util: **negrita** corta, `codigo inline` para nombres tecnicos, listas con `-` (max 5 items), links `[texto](url)`. Solo ```bloques``` cuando el usuario vaya a copiar codigo.
- URLs de deploy: una sola linea, sin formato extra.
- Texto plano, directo, sin adornos.

Regla de calidad (NO NEGOCIABLE):
- Antes del primer build/deploy de cualquier proyecto nuevo: carga `production-quality` y corre su checklist completo. NO buildes ni deployes si el checklist tiene FAILS.
- Si ves "Welcome to SvelteKit", "Edit this file", "Dashboard works!", "Get started", "Visit kit.svelte.dev" o cualquier template default en el codigo — BORRALO y ESCRIBI el contenido real del sistema. Ese es el error #1 de Papolo.
- Si la pagina se ve en blanco post-deploy: probablemente falta `{{@render children()}}` en layout o falta `import '../app.css'` para Tailwind 4. Fixea y redeploy. NO asumas que es otro error — verifica estos dos primero.
- Nunca dejes `TODO`, `FIXME`, `placeholder`, `Lorem ipsum`, codigo comentado ni implementaciones a medio hacer en archivos que se buildear.
- Cada ruta raiz (`/`) debe tener contenido real del sistema. No existe el concepto de "pagina de bienvenida" en sistemas de produccion.
- "Status: running" en Coolify NO prueba que la app funciona — solo que el container arranco. Para apps con UI, "funciona" significa que el smoke test de `agent-browser` paso (render real + login + sin errores JS). NUNCA reportes exito de una app con UI sin haber corrido el smoke test, o sin dejar constancia explicita de por que no pudiste (ej. Chrome headless no instalado en el VPS).
- **Eficiencia: hace las cosas bien la PRIMERA vez para no quemar deploys.** El primer build de cualquier app con DB ya debe incluir: `/api/health`, manejo de `PORT` (env), `/api/_seed`, conexion lazy con `MONGODB_DB_NAME`, y carga de datos via server `load` functions (NO `fetch` client-side, que rompe con cookies de sesion). Estos son requisitos del scaffold inicial, NO fixes reactivos post-deploy. Un deploy fallido por falta de health/PORT, o un dashboard que no carga datos por usar client-fetch, es un deploy desperdiciado que se evita generando bien de entrada. Meta: 3-4 deploys maximo, no 9.

{PARALLEL_BUILD_PROTOCOL}

Regla de entrega — UN SOLO TURNO (NO NEGOCIABLE):
- Cuando el usuario te encarga una app/sistema/clon, la construis ENTERA, funcional y deployada en el MISMO turno. El pedido ya es tu luz verde: NO necesitas pedir permiso para continuar tu propio trabajo.
- PROHIBIDO entregar por partes ("Deploy 1 listo, Deploy 2 va a la mitad, ¿seguimos?"), frenar a mitad de camino, o preguntar "¿seguimos?" / "¿continuo?" / "¿lo dejo funcional en 20 min mas?". Eso es un trabajo a medias disfrazado de entrega. El clon de Discord que quedo sin mensajes en tiempo real porque paraste a preguntar es EXACTAMENTE lo que hay que no hacer.
- Las fases del plan (del planner, de system-architecture, las "Fases" de las skills) son TU hoja de ruta INTERNA, no checkpoints para chequear con el usuario. Ejecutalas todas seguidas hasta que la app funcione end-to-end.
- La UNICA razon valida para frenar y preguntar es una decision de producto/negocio que solo el usuario puede tomar y que cambia QUE construis (ej. "¿suscripcion o pago unico?", "¿que dominio uso?"). Falta de permiso para seguir NO es una de esas razones.
- Cerras el turno recien cuando: la app esta deployada, el smoke test paso, y le pasas el URL. Ese es el unico "listo". Un resumen de "lo que falta" no es una entrega.

Iteraciones — NO tenes un limite duro de tool calls por respuesta. Una tarea larga (un build completo, una migracion, un refactor extenso) puede necesitar muchisimas calls y esta perfecto: segui hasta terminarla en el turno, no la cortes a la mitad. Lo unico que tenes que cuidar es no meterte en bucles ciegos: si repetis algo que ya fallo, CAMBIA de estrategia; si una tool devuelve error, maximo 2 reintentos con el mismo approach — si sigue fallando, cambia de enfoque o reportalo al usuario y pedi instrucciones en vez de girar en falso. Cada tanto el sistema te va a inyectar un chequeo anti-bucle (parar y razonar si estas avanzando de verdad); no es un freno, es para que no gires sin progreso. Si ya terminaste, deja de hacer tool calls y responde.

{REASONING_PROTOCOL}

{extra}""".strip()


@dataclass
class Agent:
    system_prompt: str | None = None
    model: str = field(default_factory=model_name)
    # Modelo para los subagentes. None => cada subagente cae a su frontmatter o al
    # default del env (model_name). El bot lo setea aparte del modelo del orquestador,
    # asi podes correr el agente principal en un modelo y los subagentes en otro.
    subagent_model: str | None = None
    max_iters: int = field(default_factory=lambda: int(os.environ.get("PAPOLO_MAX_ITERS", "0")))
    messages: list = field(default_factory=list)
    workspace_dir: str | None = None
    conversation_uuid: str | None = None
    # Flag de cancelacion cooperativa. send() la chequea entre rondas de tool calls
    # y corta en un punto seguro (sin dejar tool_calls sin su tool_result). La setea
    # otro thread (ej. el comando /papolo-stop del bot) via cancel().
    _cancel: threading.Event = field(default_factory=threading.Event, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.workspace_dir:
            self.workspace_dir = str(Path(self.workspace_dir).resolve())

        self.pipeline = PipelineTracker(self.workspace_dir)

        sys_prompt = self.system_prompt or build_system_prompt()
        if self.workspace_dir:
            sys_prompt += (
                f"\n\nWorkspace: tu directorio de trabajo aislado es `{self.workspace_dir}` "
                f"(ya tiene `git init` hecho). read_file/write_file/list_dir estan CONFINADOS a "
                f"este directorio por seguridad (paths relativos resuelven ahi; los absolutos fuera "
                f"del workspace se rechazan). `shell` sin cwd corre ahi. Trabaja siempre adentro."
            )

        if not self.messages:
            self.messages.append({"role": "system", "content": sys_prompt})

    def cancel(self) -> None:
        """Pide cancelar el turno en curso. Cooperativo: send() corta en el proximo
        checkpoint (entre rondas de tool calls), no mata tools ya en vuelo."""
        self._cancel.set()

    def all_tools(self):
        # ask_tech_stack es SOLO del orquestador (no de los subagentes): quien decide y
        # pregunta el stack es el agente principal, una vez, al arrancar la tarea.
        return (
            TOOL_SCHEMAS
            + [SKILL_TOOL_SCHEMA, SUBAGENT_TOOL_SCHEMA, ASK_TECH_STACK_SCHEMA]
            + DEPLOY_TOOL_SCHEMAS
        )

    def _loop_nudge(self, name: str, raw_args: str, result_str: str) -> str:
        """Si esta misma tool con estos mismos args ya fallo antes, agrega un nudge.
        Solo nudgea cuando el resultado actual empieza con ERROR."""
        if not result_str.lstrip().startswith("ERROR"):
            return ""
        failures = 0
        for i in range(len(self.messages) - 1, -1, -1):
            m = self.messages[i]
            if m.get("role") != "tool":
                continue
            content = str(m.get("content", ""))
            if not content.lstrip().startswith("ERROR"):
                continue
            tool_call_id = m.get("tool_call_id")
            if not tool_call_id:
                continue
            for j in range(i - 1, -1, -1):
                am = self.messages[j]
                if am.get("role") != "assistant":
                    continue
                for tc in am.get("tool_calls", []) or []:
                    if tc.get("id") != tool_call_id:
                        continue
                    fn = tc.get("function") or {}
                    if fn.get("name") == name and (fn.get("arguments") or "{}") == raw_args:
                        failures += 1
                break
            if failures >= 2:
                return (
                    "\n\n[NOTA: ya intentaste esta misma tool con args identicos al menos "
                    "2 veces antes y devolvio ERROR. Cambia el approach, no reintentes igual.]"
                )
        return ""

    def _dispatch(self, name: str, args: dict, on_event=None) -> str:
        args = resolve_path_args(name, args, self.workspace_dir)

        # Pipeline block check: build/deploy sin pasar quality check
        block = self.pipeline.should_block(name, args)
        if block:
            return block

        if name == "load_skill":
            return skill_tool_dispatch(**args)
        if name == "ask_tech_stack":
            frontend, backend, note = resolve_stack(self.conversation_uuid)
            # Registra el stack: marca stack_asked (deja de exigirlo el gate).
            self.pipeline.set_stack(frontend, backend)
            return format_stack(frontend, backend, note)
        if name == "spawn_subagent":
            sub_name = args.get("name", "")
            task = args.get("task", "")

            # Pipeline: cargar las skills que ESTE subagente necesita y pasarlas a SU
            # contexto (no al del orquestador). Antes esto rebotaba: se devolvia el texto
            # completo de las skills al orquestador y este tenia que re-spawnear. Eso
            # tenia dos costos: (1) doble round-trip por cada subagente, y (2) el reasoner
            # arrastraba 20-40k tokens de skills en el historial y los re-mandaba en CADA
            # turno del build. Peor: si el orquestador spawneaba varios implementadores en
            # paralelo, TODOS rebotaban con el dump de skills y NINGUNO implementaba,
            # rompiendo la paralelizacion. Ahora las skills van al system prompt del
            # subagente (flash, contexto efimero) y el orquestador solo ve el output final.
            to_inject = self.pipeline.skills_to_inject_for_subagent(sub_name)
            injected_skills = []
            for s in to_inject:
                content = skill_tool_dispatch(name=s)
                self.pipeline.record_result("load_skill", json.dumps({"name": s}), content)
                injected_skills.append((s, content))

            # Pipeline: enriquecer task con plan del arquitecto
            task = self.pipeline.enrich_task(task)

            out = spawn_subagent(
                name=sub_name,
                task=task,
                depth=1,
                model=self.subagent_model,
                workspace_dir=self.workspace_dir,
                conversation_uuid=self.conversation_uuid,
                on_event=on_event,
                pipeline_state=self.pipeline.summary_for_subagent(),
                injected_skills=injected_skills,
            )
            if injected_skills:
                names = ", ".join(s for s, _ in injected_skills)
                # Linea corta para que el orquestador sepa que se aplico (coherencia y
                # enforcement) sin arrastrar el texto pesado de las skills.
                out = f"[pipeline] skills aplicadas por el subagente {sub_name}: {names}\n\n{out}"
            return out
        if name in DEPLOY_DISPATCH:
            return DEPLOY_DISPATCH[name](
                workspace_dir=self.workspace_dir,
                conversation_uuid=self.conversation_uuid,
                **args,
            )
        if name in DISPATCH:
            return DISPATCH[name](**args)
        return f"Tool desconocida: {name}"

    def send(self, user_message: str, on_event=None) -> str:
        self.messages.append({"role": "user", "content": user_message})
        self.pipeline.detect_project_type(user_message)
        # El PipelineTracker se recrea fresco cada turno (bot crea un Agent nuevo por
        # mensaje), pero el historial persiste. Si en este thread ya se pregunto el stack,
        # marcarlo: es una tarea YA iniciada, no hay que re-preguntar ni volver a bloquear.
        self.pipeline.note_prior_stack(self.messages)

        # Sin tope duro de iteraciones. Lo unico que depende del scope es CUANDO arranca
        # la reflexion anti-bucle: mas tarde para un build (a iter 20 todavia scaffoldea)
        # que para una tarea simple. detect_project_type ya corrio, self.pipeline.mode es
        # confiable.
        if self.pipeline.mode == PipelineTracker.MODE_FULL_SYSTEM:
            reflexion_at = FULL_SYSTEM_REFLEXION_AT_ITER
        else:
            reflexion_at = REFLEXION_AT_ITER
        next_reflexion = reflexion_at

        client = get_client()
        event_lock = threading.Lock()

        def safe_event(kind, payload):
            if not on_event:
                return
            with event_lock:
                try:
                    on_event(kind, payload)
                except Exception:
                    pass

        iter_count = 0
        try:
          while True:
            # Cancelacion cooperativa: chequeamos al tope del loop, que es un punto
            # seguro — el estado termina en tool_results completos o en el user msg,
            # nunca con tool_calls sin responder (eso romperia la proxima API call).
            if self._cancel.is_set():
                cancelled = (
                    "[Cancelado por vos. Frené donde estaba — mandá una nueva "
                    "instrucción cuando quieras.]"
                )
                safe_event("final", {"content": cancelled})
                return cancelled
            # Kill-switch OPCIONAL del operador (PAPOLO_MAX_ITERS). Default 0 = ilimitado:
            # sin esto, el turno corre hasta que el modelo deja de pedir tools o cancelan.
            if self.max_iters > 0 and iter_count >= self.max_iters:
                break
            # Checkpoint de reflexion anti-bucle: PERIODICO, no es un limite. Hace parar y
            # razonar si esta repitiendo algo que ya fallo. No corta el turno — solo inyecta
            # un mensaje y sigue. Se repite cada REFLEXION_EVERY para atrapar loops tambien
            # en tareas larguisimas.
            if reflexion_at > 0 and iter_count >= next_reflexion:
                next_reflexion = iter_count + REFLEXION_EVERY
                self.messages.append({
                    "role": "user",
                    "content": (
                        f"[CHEQUEO ANTI-BUCLE — llevas {iter_count} iteraciones. No es un "
                        f"limite: podes seguir todo lo que la tarea necesite. Pero antes del "
                        f"proximo tool_call, para y razona en texto:\n"
                        f"1. Que intente hasta ahora y que aprendi de cada intento.\n"
                        f"2. Estoy AVANZANDO o repitiendo algo que ya fallo? Si repito, CAMBIO de estrategia.\n"
                        f"3. Cual es mi hipotesis actual de la causa raiz (si estoy debuggeando).\n"
                        f"4. Cual es el proximo paso minimo que me acerca a terminar.\n"
                        f"Si ya resolvi la tarea, deja de hacer tool calls y responde al usuario.]"
                    ),
                })
                iter_count += 1
                continue
            iter_count += 1
            resp = client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.all_tools(),
            )
            msg = resp.choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                # Soft-gate one-shot: deployaste pero no corriste el smoke test
                if self.pipeline.should_nudge_browser_test():
                    self.pipeline.browser_nudge_fired = True
                    self.messages.append({
                        "role": "user",
                        "content": (
                            "[VERIFICACION PRE-DONE — deployaste pero todavia no corriste "
                            "el smoke test de navegador. Si la app tiene UI (login, dashboard, "
                            "formularios, CRUD): carga la skill 'agent-browser', sembra la test "
                            "DB con mock data y verifica el render real contra el preview URL "
                            "(login con las creds sembradas, console/errors JS, screenshot). "
                            "Emite PASS/FAIL explicito. Si es una API pura sin frontend, validá "
                            "con `curl $PREVIEW/api/health` y dejá constancia de eso. Recien "
                            "entonces responde al usuario. Esto es one-shot: no se repite.]"
                        ),
                    })
                    iter_count += 1
                    continue
                final = msg.content or ""
                safe_event("final", {"content": final})
                return final

            # Pipeline: trackear resultados despues de cada call
            def run_call(call):
                args = json.loads(call.function.arguments or "{}")
                safe_event("tool_call", {"name": call.function.name, "args": args})
                try:
                    result = self._dispatch(call.function.name, args, on_event=safe_event)
                except Exception as e:
                    result = f"ERROR: {e}"
                safe_event("tool_result", {"name": call.function.name, "result": str(result)[:300]})
                # Pipeline: trackear resultado para estado
                self.pipeline.record_result(call.function.name, call.function.arguments or "{}", result)
                return call, result

            workers = min(len(msg.tool_calls), MAX_PARALLEL_TOOL_CALLS)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(run_call, msg.tool_calls))

            for call, result in results:
                result_str = str(result)
                nudge = self._loop_nudge(call.function.name, call.function.arguments or "{}", result_str)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_str + nudge,
                })
        finally:
            # Dejar la flag limpia para el proximo turno (agentes reusados en CLI).
            self._cancel.clear()

        last_tools = []
        for m in reversed(self.messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                last_tools = [tc["function"]["name"] for tc in m["tool_calls"]]
                break
        tail = ", ".join(last_tools) if last_tools else "?"
        return (
            f"[limite de {self.max_iters} iteraciones alcanzado. "
            f"Ultimas tools: {tail}. Subi PAPOLO_MAX_ITERS si la tarea es legitima.]"
        )


def run_agent(user_message: str, system_prompt: str | None = None) -> str:
    agent = Agent(system_prompt=system_prompt)
    return agent.send(user_message)
