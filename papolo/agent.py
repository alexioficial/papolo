import json
import os
from dataclasses import dataclass, field

from .deepseek import get_client, model_name
from .tools import TOOL_SCHEMAS, DISPATCH
from .skills import SKILL_TOOL_SCHEMA, skill_tool_dispatch, skills_index_for_prompt
from .subagents import SUBAGENT_TOOL_SCHEMA, spawn_subagent, subagents_index_for_prompt


def build_system_prompt(extra: str = "") -> str:
    return f"""Sos Papolo, un agente de IA que ayuda con tareas de software y mas.

Tenes acceso a herramientas para leer/escribir archivos, ejecutar shell, cargar skills y spawnear subagentes.

{subagents_index_for_prompt()}

{skills_index_for_prompt()}

Reglas:
- Usa las skills cuando el trigger aplica. Cargalas con load_skill antes de actuar.
- Delega en subagentes cuando la tarea es focalizada o pesada en contexto.
- Se directo y breve. Solo escribe codigo cuando te lo piden.

{extra}""".strip()


@dataclass
class Agent:
    system_prompt: str | None = None
    model: str = field(default_factory=model_name)
    max_iters: int = field(default_factory=lambda: int(os.environ.get("PAPOLO_MAX_ITERS", "25")))
    messages: list = field(default_factory=list)

    def __post_init__(self):
        sys_prompt = self.system_prompt or build_system_prompt()
        if not self.messages:
            self.messages.append({"role": "system", "content": sys_prompt})

    def all_tools(self):
        return TOOL_SCHEMAS + [SKILL_TOOL_SCHEMA, SUBAGENT_TOOL_SCHEMA]

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "load_skill":
            return skill_tool_dispatch(**args)
        if name == "spawn_subagent":
            return spawn_subagent(**args)
        if name in DISPATCH:
            return DISPATCH[name](**args)
        return f"Tool desconocida: {name}"

    def send(self, user_message: str, on_event=None) -> str:
        self.messages.append({"role": "user", "content": user_message})
        client = get_client()

        for _ in range(self.max_iters):
            resp = client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=self.all_tools(),
            )
            msg = resp.choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                if on_event:
                    on_event("final", msg.content or "")
                return msg.content or ""

            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if on_event:
                    on_event("tool_call", {"name": call.function.name, "args": args})
                try:
                    result = self._dispatch(call.function.name, args)
                except Exception as e:
                    result = f"ERROR: {e}"
                if on_event:
                    on_event("tool_result", {"name": call.function.name, "result": result})
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result),
                })

        return "[limite de iteraciones alcanzado]"


def run_agent(user_message: str, system_prompt: str | None = None) -> str:
    agent = Agent(system_prompt=system_prompt)
    return agent.send(user_message)
