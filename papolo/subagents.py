from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import os
import yaml

from .deepseek import get_client, model_name
from .tools import TOOL_SCHEMAS, DISPATCH
from .skills import SKILL_TOOL_SCHEMA, skill_tool_dispatch

SUBAGENTS_DIR = Path(__file__).resolve().parent.parent / "subagents"
MAX_PARALLEL_TOOL_CALLS = int(os.environ.get("PAPOLO_MAX_PARALLEL", "8"))


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
        "description": "Crea un subagente especializado con su propio contexto. Util para tareas focalizadas o para no contaminar el contexto principal. Podes invocar varios spawn_subagent en una misma respuesta y corren en paralelo.",
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


def _sub_dispatch(name: str, args: dict) -> str:
    if name == "load_skill":
        return skill_tool_dispatch(**args)
    if name in DISPATCH:
        return DISPATCH[name](**args)
    return f"Tool desconocida: {name}"


def spawn_subagent(name: str, task: str, max_iters: int = 15) -> str:
    md_path = SUBAGENTS_DIR / f"{name}.md"
    if not md_path.exists():
        return f"Subagente '{name}' no encontrado"

    meta, system_prompt = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    sub_model = meta.get("model", model_name())

    client = get_client()
    tools = TOOL_SCHEMAS + [SKILL_TOOL_SCHEMA]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for _ in range(max_iters):
        resp = client.chat.completions.create(
            model=sub_model,
            messages=messages,
            tools=tools,
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or ""

        def run_call(call):
            args = json.loads(call.function.arguments or "{}")
            try:
                result = _sub_dispatch(call.function.name, args)
            except Exception as e:
                result = f"ERROR: {e}"
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

    return "[subagente alcanzo el limite de iteraciones]"
