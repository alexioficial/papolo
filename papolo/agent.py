import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .deepseek import get_client, model_name
from .tools import TOOL_SCHEMAS, DISPATCH
from .skills import SKILL_TOOL_SCHEMA, skill_tool_dispatch, skills_index_for_prompt
from .subagents import SUBAGENT_TOOL_SCHEMA, spawn_subagent, subagents_index_for_prompt
from .deploy import DEPLOY_TOOL_SCHEMAS, DEPLOY_DISPATCH, deploy_index_for_prompt
from .pipeline import PipelineTracker


MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("PAPOLO_MAX_PARALLEL", "8"))
PER_CALL_MAX_ITERS = int(os.environ.get("PAPOLO_PER_CALL_MAX_ITERS", "50"))


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

Skills criticas — cargalas OBLIGATORIAMENTE segun el contexto:
- Cuando construyas un sistema/app/proyecto con interfaz visual: carga `system-architecture` (diseno arquitectonico), `professional-ui-design` (diseno UI profesional con anti-AI-slop) y `ux-methodology` (experiencia de usuario completa). Cargalas DESPUES del planner y ANTES de implementar.
- Cuando implementes componentes UI o SvelteKit: carga `professional-ui-design` primero — genera DESIGN.md completo antes de tocar codigo. Sigue sus reglas anti-AI-slop (nada de gradients purple, Inter font, em-dash, nombres genericos, tarjetas de 3 columnas iguales).
- ANTES de buildear o deployar: carga `production-quality`. Verifica que el codigo no tenga placeholders, templates default, "Welcome to SvelteKit", +page.svelte sin contenido real, falta de import '../app.css', ni implementaciones a medias. Si encuentra algo, lo fixea antes de buildear.
- Para deploy: carga `coolify-deploy` (templates Dockerfile, polling, cache busting).
- Las skills existentes siguen disponibles: `code-review`, `debugging-systematic`, `git-workflow`, `writing-tests`, `refactoring-safely`, `web-search`, `search-docs`.

Planificacion (NO opcional):
- Si el usuario pide construir "un sistema", "una app", "un proyecto", "una plataforma" o similar — TU PRIMER tool_call es siempre `spawn_subagent` al `planner`. Sin excepciones. El planner tiene que cubrir: features explicitas + features implicitas obvias (auth/login si maneja usuarios o datos privados, roles/permisos si el dominio tiene cargos diferenciados ej. ventas tiene vendedor/admin/cliente, validacion server-side, manejo de errores, casos vacios, paginacion, edge cases del dominio).
- NO empieces a escribir codigo hasta tener el plan del planner en mano. NO improvises arquitectura.
- Si el usuario pide algo trivial (cambiar un color, fixear un typo), saltea el planner.

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

Iteraciones — tu tienes un limite de ~50 tool calls por respuesta. Si llegas a 50 sin haber respondido, el sistema te va a pedir que resumas urgentemente. No entres en loops de debug sin progreso visible. Si una tool devuelve error, maximo 2 reintentos — si sigue fallando, reportalo al usuario y pedi instrucciones en vez de seguir intentando solo.

{extra}""".strip()


def _resolve_path_args(name: str, args: dict, workspace_dir: str | None) -> dict:
    if not workspace_dir:
        return args
    args = dict(args)
    if name in ("read_file", "write_file", "list_dir") and "path" in args:
        p = Path(args["path"])
        if not p.is_absolute():
            args["path"] = str(Path(workspace_dir) / p)
    elif name == "shell":
        cwd = args.get("cwd")
        if not cwd:
            args["cwd"] = workspace_dir
        elif not Path(cwd).is_absolute():
            args["cwd"] = str(Path(workspace_dir) / cwd)
    return args


@dataclass
class Agent:
    system_prompt: str | None = None
    model: str = field(default_factory=model_name)
    max_iters: int = field(default_factory=lambda: int(os.environ.get("PAPOLO_MAX_ITERS", "0")))
    messages: list = field(default_factory=list)
    workspace_dir: str | None = None
    conversation_uuid: str | None = None

    def __post_init__(self):
        if self.workspace_dir:
            self.workspace_dir = str(Path(self.workspace_dir).resolve())

        self.pipeline = PipelineTracker(self.workspace_dir)

        sys_prompt = self.system_prompt or build_system_prompt()
        if self.workspace_dir:
            sys_prompt += (
                f"\n\nWorkspace: tu directorio de trabajo aislado es `{self.workspace_dir}` "
                f"(ya tiene `git init` hecho). Todos los read_file/write_file/list_dir con paths "
                f"relativos resuelven ahi. `shell` sin cwd corre ahi. Trabaja siempre dentro de este "
                f"directorio salvo que necesites algo afuera explicitamente."
            )

        if not self.messages:
            self.messages.append({"role": "system", "content": sys_prompt})

    def all_tools(self):
        return TOOL_SCHEMAS + [SKILL_TOOL_SCHEMA, SUBAGENT_TOOL_SCHEMA] + DEPLOY_TOOL_SCHEMAS

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
        args = _resolve_path_args(name, args, self.workspace_dir)

        # Pipeline block check: build/deploy sin pasar quality check
        block = self.pipeline.should_block(name, args)
        if block:
            return block

        if name == "load_skill":
            return skill_tool_dispatch(**args)
        if name == "spawn_subagent":
            sub_name = args.get("name", "")
            task = args.get("task", "")

            # Pipeline: inyeccion de skills faltantes
            missing = self.pipeline.missing_skills_for_subagent(sub_name)
            if missing:
                results = []
                for s in missing:
                    content = skill_tool_dispatch(name=s)
                    self.pipeline.record_result(
                        "load_skill", json.dumps({"name": s}), content
                    )
                    results.append(
                        f"[PIPELINE] Skill '{s}' cargada:\n\n{content}"
                    )
                return "\n\n---\n\n".join(results)

            # Pipeline: enriquecer task con plan del arquitecto
            task = self.pipeline.enrich_task(task)

            return spawn_subagent(
                name=sub_name,
                task=task,
                depth=1,
                workspace_dir=self.workspace_dir,
                conversation_uuid=self.conversation_uuid,
                on_event=on_event,
            )
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
        forced_cap = False
        while True:
            if self.max_iters > 0 and iter_count >= self.max_iters:
                break
            if not forced_cap and iter_count >= PER_CALL_MAX_ITERS:
                forced_cap = True
                self.messages.append({
                    "role": "user",
                    "content": (
                        f"[Has usado {iter_count} iteraciones en esta respuesta. "
                        f"Es hora de resumir y responder al usuario con lo que tienes. "
                        f"No hagas mas tool calls. Responde en maximo 3 parrafos.]"
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
