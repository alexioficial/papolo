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


MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("PAPOLO_MAX_PARALLEL", "8"))


def build_system_prompt(extra: str = "") -> str:
    deploy_block = deploy_index_for_prompt()
    return f"""Papolo, un agente de IA que ayuda con tareas de software y mas.

Tenes acceso a herramientas para leer/escribir archivos, ejecutar shell, cargar skills y spawnear subagentes.

{subagents_index_for_prompt()}

{skills_index_for_prompt()}

{deploy_block}

Reglas:
- Usa las skills cuando el trigger aplica. Cargalas con load_skill antes de actuar.
- Delega en subagentes cuando la tarea es focalizada o pesada en contexto.
- Cuando tengas varias acciones independientes (varias lecturas, varios subagentes, varios shell), emitilas como multiples tool_calls en la MISMA respuesta. Se ejecutan en paralelo. Solo serializa cuando una depende del resultado de otra.
- Usa git para tus cambios: antes de modificaciones riesgosas commiteas (`git add -A && git commit -m '...'`), asi podes revertir con `git reset --hard HEAD~1` si algo sale mal. Brancheas con `git checkout -b experimento` cuando explores.
- Para web/python apps tenes node, pnpm, python, uv, cargo disponibles en el shell. Antes de deployar, valida que builda local.
- Se directo y breve. Solo escribe codigo cuando te lo piden.

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

    def _dispatch(self, name: str, args: dict, on_event=None) -> str:
        args = _resolve_path_args(name, args, self.workspace_dir)
        if name == "load_skill":
            return skill_tool_dispatch(**args)
        if name == "spawn_subagent":
            return spawn_subagent(
                name=args.get("name"),
                task=args.get("task"),
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
        while True:
            if self.max_iters > 0 and iter_count >= self.max_iters:
                break
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

            def run_call(call):
                args = json.loads(call.function.arguments or "{}")
                safe_event("tool_call", {"name": call.function.name, "args": args})
                try:
                    result = self._dispatch(call.function.name, args, on_event=safe_event)
                except Exception as e:
                    result = f"ERROR: {e}"
                safe_event("tool_result", {"name": call.function.name, "result": str(result)[:300]})
                return call, result

            workers = min(len(msg.tool_calls), MAX_PARALLEL_TOOL_CALLS)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(run_call, msg.tool_calls))

            for call, result in results:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result),
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
