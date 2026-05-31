from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import os
import yaml

from .deepseek import get_client, model_name
from .tools import TOOL_SCHEMAS, DISPATCH
from .skills import SKILL_TOOL_SCHEMA, skill_tool_dispatch
from .deploy import DEPLOY_TOOL_SCHEMAS, DEPLOY_DISPATCH

SUBAGENTS_DIR = Path(__file__).resolve().parent.parent / "subagents"
MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("PAPOLO_MAX_PARALLEL", "8"))
MAX_SUBAGENT_DEPTH = int(os.environ.get("PAPOLO_MAX_DEPTH", "3"))


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    try:
        meta = yaml.safe_load(text[3:end].strip()) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[end + 4 :].lstrip("\n")


def list_subagents() -> list[dict]:
    out = []
    if not SUBAGENTS_DIR.exists():
        return out
    for md in sorted(SUBAGENTS_DIR.glob("*.md")):
        if md.stem.startswith("_"):
            continue
        meta, _ = _parse_frontmatter(md.read_text(encoding="utf-8"))
        out.append({
            "name": meta.get("name", md.stem),
            "description": meta.get("description", ""),
            "model": meta.get("model", model_name()),
            "path": str(md),
        })
    return out


def subagents_index_for_prompt() -> str:
    subs = list_subagents()
    if not subs:
        return "(sin subagentes definidos)"
    lines = ["Subagentes disponibles via spawn_subagent:"]
    for s in subs:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines)


SUBAGENT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "spawn_subagent",
        "description": (
            "Crea un subagente especializado con su propio contexto. Util para tareas focalizadas o "
            "para no contaminar el contexto principal. Podes invocar varios spawn_subagent en una "
            "misma respuesta y corren en paralelo. Los subagentes pueden a su vez spawnear mas "
            f"subagentes hasta una profundidad maxima de {MAX_SUBAGENT_DEPTH}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del subagente"},
                "task": {"type": "string", "description": "Descripcion completa y autocontenida de la tarea"},
            },
            "required": ["name", "task"],
        },
    },
}


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


def spawn_subagent(
    name: str,
    task: str,
    max_iters: int | None = None,
    depth: int = 1,
    workspace_dir: str | None = None,
    conversation_uuid: str | None = None,
    on_event=None,
) -> str:
    if max_iters is None:
        max_iters = int(os.environ.get("PAPOLO_SUBAGENT_MAX_ITERS", "0"))

    def emit(kind: str, payload: dict) -> None:
        if on_event is None:
            return
        on_event(kind, {**payload, "subagent": name, "depth": depth})

    emit("subagent_start", {"task": task})
    if depth > MAX_SUBAGENT_DEPTH:
        return (
            f"ERROR: limite de profundidad de subagentes ({MAX_SUBAGENT_DEPTH}) alcanzado. "
            "Resolve la tarea con las tools directas en lugar de spawnear mas subagentes."
        )

    md_path = SUBAGENTS_DIR / f"{name}.md"
    if not md_path.exists():
        return f"Subagente '{name}' no encontrado"

    meta, system_prompt = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    sub_model = meta.get("model", model_name())

    if workspace_dir:
        system_prompt += (
            f"\n\nWorkspace asignado: `{workspace_dir}` (ya tiene `git init` hecho). "
            f"Paths relativos resuelven ahi. `shell` sin cwd corre ahi. "
            f"Usa git commit antes de cambios riesgosos para poder revertir."
        )

    client = get_client()
    tools = TOOL_SCHEMAS + [SKILL_TOOL_SCHEMA, SUBAGENT_TOOL_SCHEMA] + DEPLOY_TOOL_SCHEMAS
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    def sub_dispatch(tname: str, targs: dict) -> str:
        targs = _resolve_path_args(tname, targs, workspace_dir)
        if tname == "load_skill":
            return skill_tool_dispatch(**targs)
        if tname == "spawn_subagent":
            return spawn_subagent(
                name=targs.get("name"),
                task=targs.get("task"),
                depth=depth + 1,
                workspace_dir=workspace_dir,
                conversation_uuid=conversation_uuid,
                on_event=on_event,
            )
        if tname in DEPLOY_DISPATCH:
            return DEPLOY_DISPATCH[tname](
                workspace_dir=workspace_dir,
                conversation_uuid=conversation_uuid,
                **targs,
            )
        if tname in DISPATCH:
            return DISPATCH[tname](**targs)
        return f"Tool desconocida: {tname}"

    sub_iter = 0
    while True:
        if max_iters > 0 and sub_iter >= max_iters:
            break
        sub_iter += 1
        resp = client.chat.completions.create(
            model=sub_model,
            messages=messages,
            tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            final = msg.content or ""
            emit("subagent_end", {"final": final[:200]})
            return final

        def run_call(call):
            args = json.loads(call.function.arguments or "{}")
            emit("tool_call", {"name": call.function.name, "args": args})
            try:
                result = sub_dispatch(call.function.name, args)
            except Exception as e:
                result = f"ERROR: {e}"
            emit("tool_result", {"name": call.function.name, "result": str(result)[:300]})
            return call, result

        workers = min(len(msg.tool_calls), MAX_PARALLEL_TOOL_CALLS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_call, msg.tool_calls))

        for call, result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })

    emit("subagent_end", {"final": "[limite iters]"})
    return "[subagente alcanzo el limite de iteraciones]"
