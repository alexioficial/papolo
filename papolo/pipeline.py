"""
Pipeline enforcement para Papolo.

Tres mecanismos combinados para que Papolo NO pueda saltarse el pipeline:

1. INYECCION (en _dispatch): cuando Papolo intenta spawnear un subagente
   implementador sin las skills requeridas, se cargan automaticamente y se
   devuelve su contenido AL subagente. Papolo las ve y las aplica.

2. BLOQUEO (en _dispatch): build/deploy commands se interceptan y bloquean
   si production-quality no ha pasado. El modelo recibe un mensaje de bloqueo.

3. ENRIQUECIMIENTO (en _dispatch): el output del planner se attacha
   automaticamente al task de los subagentes implementadores.
"""

import json
import re
from typing import Optional


class PipelineTracker:
    """Trackea el estado del pipeline y expone metodos de enforcement.

    No hace inyeccion de tool_calls — todo se resuelve en _dispatch().
    """

    # Modos de proyecto
    MODE_CONVERSATION = "conversation"
    MODE_SIMPLE_TOOL = "simple_tool"
    MODE_FULL_SYSTEM = "full_system"

    def __init__(self, workspace_dir: Optional[str] = None):
        self.workspace_dir = workspace_dir
        self.skills_loaded: set[str] = set()
        self.planner_output: Optional[str] = None
        self.production_quality_loaded: bool = False
        self.production_check_passed: bool = False
        self.mode: str = self.MODE_CONVERSATION

    # ── Deteccion ──────────────────────────────────────────────

    def detect_project_type(self, user_message: str):
        """Detecta el modo del proyecto basado en el mensaje del usuario.

        Tres modos:
        - CONVERSATION: preguntas, consultas, busquedas. Sin codigo.
        - SIMPLE_TOOL: landing, calculadora, generador. Sin auth/DB.
        - FULL_SYSTEM: app multi-pagina con auth, DB, CRUD, roles.
        """
        msg = user_message.lower()

        # Palabras que indican sistema completo
        full_system_kw = [
            "sistema de", "app con auth", "app con login", "app con roles",
            "app con crud", "app con base de datos", "app con mongodb",
            "plataforma de", "sistema completo", "api con", "backend con",
            "dashboard con", "panel de administracion",
        ]
        # Palabras que indican herramienta simple
        simple_tool_kw = [
            "landing page", "pagina de aterrizaje", "calculadora",
            "contador", "portafolio", "pagina personal", "generador",
            "convertidor", "pagina de una sola", "pagina one-shot",
            "pagina estatica", "pagina simple", "widget", "tool", "herramienta",
            "pagina de", "pagina para",
        ]
        # Palabras que indican conversacion
        conversation_kw = [
            "que es", "como se", "puedes explicar", "busca en internet",
            "investiga", "que opinas", "que sabes", "ayudame con",
            "que significa", "dime sobre",
        ]

        if any(kw in msg for kw in full_system_kw):
            self.mode = self.MODE_FULL_SYSTEM
        elif any(kw in msg for kw in simple_tool_kw):
            self.mode = self.MODE_SIMPLE_TOOL
        elif any(kw in msg for kw in conversation_kw):
            self.mode = self.MODE_CONVERSATION
        else:
            # Por defecto: si menciona construir/crear algo, asumir simple tool
            # Si solo pregunta, asumir conversation
            if any(kw in msg for kw in ["construye", "crea", "haz", "build"]):
                self.mode = self.MODE_SIMPLE_TOOL
            else:
                self.mode = self.MODE_CONVERSATION

    # ── Mecanismo 1: Inyeccion de skills en spawn_subagent ─────

    def missing_skills_for_subagent(self, subagent_name: str) -> list[str]:
        """Skills que deben cargarse ANTES de spawnear este subagente.

        Devuelve lista vacia si no faltan skills.
        Segun el modo, requiere diferentes skills:
        - FULL_SYSTEM: architecture + design + ux + ui-ux-pro-max
        - SIMPLE_TOOL: solo professional-ui-design
        - CONVERSATION: ninguna
        """
        if subagent_name in ("planner", ""):
            return []
        if self.mode == self.MODE_CONVERSATION:
            return []

        missing = []
        # Ambos modos (simple tool y full system) necesitan diseño profesional
        if "professional-ui-design" not in self.skills_loaded:
            missing.append("professional-ui-design")

        # Solo full system necesita arquitectura y UX completo
        if self.mode == self.MODE_FULL_SYSTEM:
            if "system-architecture" not in self.skills_loaded:
                missing.append("system-architecture")
            if "ux-methodology" not in self.skills_loaded:
                missing.append("ux-methodology")
            if "ui-ux-pro-max" not in self.skills_loaded:
                missing.append("ui-ux-pro-max")

        return missing

    def enrich_task(self, task: str) -> str:
        """Attacha planner output al task si existe y no esta ya attachado."""
        if self.planner_output and "Plan del arquitecto" not in task and "## ARCH" not in task:
            plan = self.planner_output[:2000]
            return f"{task}\n\n---\nPlan del arquitecto:\n{plan}\n---"
        return task

    # ── Mecanismo 2: Bloqueo de build/deploy ───────────────────

    def should_block(self, name: str, args: dict) -> Optional[str]:
        """Devuelve mensaje de bloqueo si la call debe bloquearse, None si pasa."""
        if name == "shell" and self._is_build_cmd(args):
            if "production-quality" not in self.skills_loaded:
                return (
                    "[PIPELINE] No podes buildear sin cargar 'production-quality' primero. "
                    "Usa load_skill('production-quality') y corre su checklist completo."
                )
            if self.production_quality_loaded and not self.production_check_passed:
                return (
                    "[PIPELINE] El production-quality check no paso. "
                    "Corregi los FAILS reportados antes de reintentar el build."
                )

        if name in ("coolify_deploy",):
            if not self.production_check_passed:
                if "production-quality" not in self.skills_loaded:
                    return (
                        "[PIPELINE] No podes deployar sin cargar 'production-quality' primero. "
                        "Usa load_skill('production-quality') y corre su checklist."
                    )
                return (
                    "[PIPELINE] No podes deployar sin pasar el production-quality check. "
                    "Corregi los FAILS antes de deployar."
                )

        return None

    # ── Tracking de resultados ─────────────────────────────────

    def record_result(self, name: str, args_raw: str, result: str):
        """Registra el resultado de una tool call para actualizar el estado."""
        args = json.loads(args_raw or "{}")

        if name == "load_skill":
            skill = args.get("name", "")
            self.skills_loaded.add(skill)
            if skill == "production-quality":
                self.production_quality_loaded = True

        elif name == "spawn_subagent":
            if args.get("name") == "planner":
                self.planner_output = result

        # Detectar si production-quality paso
        if self.production_quality_loaded and not self.production_check_passed:
            if "APTO PARA DEPLOY" in result or ("[PASS]" in result and "[FAIL]" not in result):
                self.production_check_passed = True

    def _is_build_cmd(self, args: dict) -> bool:
        cmd = args.get("command", "")
        return bool(re.search(
            r"\b(pnpm build|npm run build|cargo build|go build|uv build)\b", cmd
        ))
