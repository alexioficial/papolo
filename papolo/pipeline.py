"""
Pipeline enforcement para Papolo.

Tres mecanismos combinados para que Papolo NO pueda saltarse el pipeline:

1. INYECCION (en _dispatch): al spawnear un subagente implementador, las skills
   que su rol requiere (segun el modo) se cargan automaticamente y se inyectan en
   EL SYSTEM PROMPT DEL SUBAGENTE — no en el del orquestador. Cada worker recibe su
   propia copia (indispensable si se spawnean varios en paralelo) y el reasoner
   principal queda liviano en vez de arrastrar el texto de las skills cada turno.

2. BLOQUEO (en _dispatch): build/deploy commands se interceptan y bloquean
   si production-quality no ha pasado. El modelo recibe un mensaje de bloqueo.

3. ENRIQUECIMIENTO (en _dispatch): el output del planner se attacha
   automaticamente al task de los subagentes implementadores.
"""

import json
import re
import threading
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
        # Las tool calls de un mismo turno corren en paralelo (ThreadPoolExecutor en
        # agent.py/subagents.py) y todas mutan/leen este tracker. Con la paralelizacion
        # de implementadores eso es la norma, no la excepcion, asi que el estado
        # compartido va protegido: sin el lock, un sorted(skills_loaded) mientras otro
        # thread hace add() revienta con "Set changed size during iteration".
        self._lock = threading.RLock()
        self.skills_loaded: set[str] = set()
        self.planner_output: Optional[str] = None
        self.production_quality_loaded: bool = False
        self.production_check_passed: bool = False
        self.mode: str = self.MODE_CONVERSATION
        # Tech stack: True una vez que se corrio ask_tech_stack (o se detecto que ya se
        # corrio antes en el thread). Hasta entonces, en modo build, se bloquea spawnear
        # planner/expertos y buildear — primero hay que preguntarle el stack al usuario.
        self.stack_asked: bool = False
        # True si el frontend elegido es Flutter: su compilacion/deploy no esta cableado,
        # asi que el frontend NO se sube a Coolify (sin preview) — solo el backend se deploya.
        self.flutter_frontend: bool = False
        # True si el pedido huele a tiempo real (chat, notificaciones, presencia,
        # feed live, colaboracion, multiplayer). Fuerza la skill realtime-architecture.
        self.realtime_hint: bool = False

        # Deploy failure tracking
        self.deploy_attempts: dict[str, int] = {}
        self.last_deploy_unhealthy: bool = False
        self.unhealthy_app_uuid: str | None = None
        self.deploy_consecutive_failures: int = 0

        # Smoke test de navegador tracking
        self.deploy_happened: bool = False        # hubo al menos un coolify_deploy
        self.browser_tested: bool = False         # se corrio agent-browser desde el ultimo deploy
        self.browser_nudge_fired: bool = False    # soft-gate one-shot ya disparado

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
        # Nombres de apps multi-usuario: aunque no digan "auth", necesitan identidad +
        # DB + roles. Un chat/red social/foro/clon sin auth ni persistencia esta mal
        # construido. Pero SOLO cuentan como sistema si hay verbo de construccion y no
        # es una pregunta — "que es un chat" o "que opinas de discord" NO son builds.
        multiuser_kw = [
            "chat", "mensajeria", "mensajería", "red social", "foro",
            "clon de", "multijugador", "multiplayer", "colaborativ", "discord",
        ]
        build_verbs = [
            "construye", "construi", "crea", "cre", "haz", "hace", "arma", "armá",
            "build", "programa", "desarrolla", "implementa", "hacer",
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

        is_question = any(kw in msg for kw in conversation_kw)

        if any(kw in msg for kw in full_system_kw):
            self.mode = self.MODE_FULL_SYSTEM
        elif (
            any(kw in msg for kw in multiuser_kw)
            and any(v in msg for v in build_verbs)
            and not is_question
        ):
            # "hazme un clon de discord", "crea un chat" → sistema multi-usuario
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

        self.realtime_hint = self._detect_realtime(msg)

    def set_stack(self, frontend: str, backend: str) -> None:
        """Registra el stack elegido. Marca stack_asked y el flag de frontend Flutter."""
        self.stack_asked = True
        self.flutter_frontend = (frontend == "flutter")

    def note_prior_stack(self, messages: list) -> None:
        """Marca stack_asked (y flutter_frontend) si ya se llamo ask_tech_stack en el thread.

        El tracker se recrea fresco cada turno, pero el stack elegido vive en los
        mensajes persistidos. Sin esto, un mensaje de seguimiento en una tarea ya
        iniciada re-dispararia el gate (y el pedido de re-elegir stack), y se perderia
        el flag de Flutter que evita subir el frontend a Coolify."""
        ask_ids: set[str] = set()
        for m in messages:
            if m.get("role") != "assistant":
                continue
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function") or {}
                if fn.get("name") == "ask_tech_stack":
                    self.stack_asked = True
                    if tc.get("id"):
                        ask_ids.add(tc["id"])
        # El resultado de ask_tech_stack (tool message) menciona `flutter-dart-expert`
        # cuando el frontend elegido fue Flutter — de ahi recuperamos el flag.
        if ask_ids:
            for m in messages:
                if (
                    m.get("role") == "tool"
                    and m.get("tool_call_id") in ask_ids
                    and "flutter-dart-expert" in str(m.get("content", ""))
                ):
                    self.flutter_frontend = True
                    break

    def _detect_realtime(self, msg: str) -> bool:
        """True si el pedido implica datos push (cambios de otros usuarios en vivo).

        Estos dominios necesitan SSE/WebSocket, no polling. El clasico error de
        Papolo fue resolver un chat con setInterval/fetch.
        """
        realtime_kw = [
            "tiempo real", "real-time", "realtime", "en vivo", "live",
            "chat", "mensajeria", "mensajería", "mensajes", "messaging",
            "notificacion", "notificación", "notificaciones",
            "presencia", "en linea", "en línea", "online",
            "escribiendo", "typing", "websocket", "socket", "sse",
            "colaborativ", "colabora", "multiplayer", "multijugador",
            "feed en vivo", "streaming", "subasta", "puja", "bidding",
            "discord", "slack", "whatsapp", "telegram", "messenger",
        ]
        return any(kw in msg for kw in realtime_kw)

    # ── Mecanismo 1: Inyeccion de skills en spawn_subagent ─────

    def skills_to_inject_for_subagent(self, subagent_name: str) -> list[str]:
        """Skills que ESTE subagente necesita en su propio contexto, segun rol y modo.

        A diferencia de `missing_skills_for_subagent`, NO se filtra por skills ya
        cargadas: cada subagente arranca con contexto fresco (sobre todo los workers
        paralelos), asi que necesita SU copia de las skills aunque otro subagente ya
        las haya usado. Se inyectan en el system prompt del subagente — nunca en el del
        orquestador — que es lo que mantiene liviano al reasoner: en vez de arrastrar
        20-40k tokens de skills en cada turno del agente principal, el texto pesado vive
        una sola vez en el contexto efimero de un subagente flash.

        - FULL_SYSTEM: professional-ui-design + system-architecture + ux-methodology +
          ui-ux-pro-max + reachability-audit.
        - SIMPLE_TOOL: solo professional-ui-design.
        - CONVERSATION / planner: ninguna.
        - Cualquier modo con hint de tiempo real: + realtime-architecture.
        """
        if subagent_name in ("planner", ""):
            return []
        if self.mode == self.MODE_CONVERSATION:
            return []

        skills = ["professional-ui-design"]
        if self.mode == self.MODE_FULL_SYSTEM:
            skills += [
                "system-architecture",
                "ux-methodology",
                "ui-ux-pro-max",
                "reachability-audit",
            ]
        if self.realtime_hint:
            skills.append("realtime-architecture")
        return skills

    def enrich_task(self, task: str) -> str:
        """Attacha planner output al task si existe y no esta ya attachado."""
        if self.planner_output and "Plan del arquitecto" not in task and "## ARCH" not in task:
            plan = self.planner_output[:2000]
            return f"{task}\n\n---\nPlan del arquitecto:\n{plan}\n---"
        return task

    # ── Mecanismo 2: Bloqueo de build/deploy ───────────────────

    def should_block(self, name: str, args: dict) -> Optional[str]:
        """Devuelve mensaje de bloqueo si la call debe bloquearse, None si pasa."""
        # Gate de tech stack: en modo build, no se planea/construye antes de preguntarle
        # el stack al usuario. ask_tech_stack en si nunca se bloquea (no es spawn/shell/deploy).
        if (
            not self.stack_asked
            and self.mode in (self.MODE_SIMPLE_TOOL, self.MODE_FULL_SYSTEM)
        ):
            if name == "spawn_subagent":
                return (
                    "[PIPELINE] Antes de planear o construir tenes que preguntarle el stack "
                    "al usuario. Tu primer tool_call debe ser `ask_tech_stack` (solo, sin nada "
                    "mas): le muestra el menu de frontend/backend por reacciones y te devuelve "
                    "su eleccion. Recien con el stack elegido spawnea el planner o los expertos."
                )
            if name == "coolify_deploy" or (name == "shell" and self._is_build_cmd(args)):
                return (
                    "[PIPELINE] Todavia no preguntaste el stack (`ask_tech_stack`). No podes "
                    "buildear ni deployar antes de que el usuario elija frontend + backend."
                )

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
            # Gate: production-quality check
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

            # Gate: deploy unhealthy — forzar diagnostico antes de reintentar
            app_uuid = args.get("app_uuid", "unknown")
            attempts = self.deploy_attempts.get(app_uuid, 0)
            if self.last_deploy_unhealthy:
                # El PRIMER unhealthy (solo 1 deploy previo) suele ser un transitorio del
                # primer deploy de Coolify (la app arranca local; un redeploy con el mismo
                # codigo queda running). Permitimos UN redeploy sin el detour de diagnostico,
                # SIEMPRE que el modelo haya verificado arranque local (node build).
                # Recien si el SEGUNDO deploy tambien queda unhealthy, forzamos diagnostico.
                if attempts >= 2 and "debugging-systematic" not in self.skills_loaded:
                    return (
                        f"[PIPELINE] Van {attempts} deploys y sigue unhealthy — ya no es el "
                        "transitorio del primer deploy, hay un problema real. NO reintentes "
                        "sin diagnosticar.\n"
                        "1. Carga 'debugging-systematic' con load_skill.\n"
                        "2. Verifica: arranca local (`npm run build` + `timeout 6 node build`)? "
                        "envs seteadas? conexion lazy a DB? puerto correcto?\n"
                        "3. Solo despues de diagnosticar, fixea y redeploya."
                    )
                # Hard cap: 3 intentos unhealthy maximo
                if attempts >= 3:
                    return (
                        f"[PIPELINE] Ya intentaste deployar {attempts} veces y sigue "
                        "unhealthy. No reintentes mas solo. Reporta al usuario:\n"
                        f"- Estado actual de la app\n"
                        f"- Que diagnosticaste hasta ahora\n"
                        f"- Que informacion necesitas para resolverlo\n"
                        "Pedi instrucciones explicitas."
                    )

        return None

    # ── Tracking de resultados ─────────────────────────────────

    def record_result(self, name: str, args_raw: str, result: str):
        """Registra el resultado de una tool call para actualizar el estado.

        Corre bajo lock: lo llaman en paralelo los workers de un mismo turno."""
        args = json.loads(args_raw or "{}")

        with self._lock:
            if name == "load_skill":
                skill = args.get("name", "")
                self.skills_loaded.add(skill)
                if skill == "production-quality":
                    self.production_quality_loaded = True
                # Cargar debugging-systematic resetea unhealthy flag
                if skill == "debugging-systematic" and self.last_deploy_unhealthy:
                    self.last_deploy_unhealthy = False

            elif name == "spawn_subagent":
                if args.get("name") == "planner":
                    self.planner_output = result

            elif name == "coolify_deploy":
                app_uuid = args.get("app_uuid", "unknown")
                self.deploy_attempts[app_uuid] = self.deploy_attempts.get(app_uuid, 0) + 1
                # Cada deploy reabre la obligacion de smoke-testear
                self.deploy_happened = True
                self.browser_tested = False
                self.browser_nudge_fired = False
                # Si el resultado menciona unhealthy, marcarlo
                if "unhealthy" in result.lower() or "failed" in result.lower():
                    self.last_deploy_unhealthy = True
                    self.unhealthy_app_uuid = app_uuid
                    self.deploy_consecutive_failures += 1

            elif name == "shell":
                # Detectar si corrio el smoke test de navegador
                if "agent-browser" in args.get("command", ""):
                    self.browser_tested = True

            elif name == "coolify_status":
                if "unhealthy" in result.lower() or "exited" in result.lower():
                    self.last_deploy_unhealthy = True
                elif "running" in result.lower() and "healthy" in result.lower():
                    self.last_deploy_unhealthy = False
                    self.unhealthy_app_uuid = None
                    self.deploy_consecutive_failures = 0

            # Detectar si production-quality paso
            if self.production_quality_loaded and not self.production_check_passed:
                if "APTO PARA DEPLOY" in result or ("[PASS]" in result and "[FAIL]" not in result):
                    self.production_check_passed = True

    def should_nudge_browser_test(self) -> bool:
        """True si hay que recordarle al modelo que corra el smoke test de navegador
        antes de dar la respuesta final. Soft-gate one-shot (no es un block duro:
        el pipeline no sabe con certeza si la app tiene UI)."""
        return (
            self.deploy_happened
            and self.mode != self.MODE_CONVERSATION
            and not self.browser_tested
            and not self.browser_nudge_fired
        )

    def summary_for_subagent(self) -> str:
        """Resumen del estado del pipeline para inyectar en system prompt de subagentes."""
        parts = []
        if self.production_check_passed:
            parts.append("- production-quality check: PASSED")
        else:
            parts.append("- production-quality check: NOT PASSED")
        with self._lock:
            loaded_snapshot = sorted(self.skills_loaded)
        if loaded_snapshot:
            parts.append(f"- Skills cargadas: {', '.join(loaded_snapshot)}")
        if self.last_deploy_unhealthy:
            parts.append("- ULTIMO DEPLOY: FALLIDO (unhealthy) - diagnosticar antes de reintentar")
        if self.deploy_happened and not self.browser_tested:
            parts.append("- Smoke test de navegador: PENDIENTE (corré agent-browser antes de done)")
        if self.flutter_frontend:
            parts.append(
                "- Frontend Flutter: NO se sube a Coolify (sin app ni preview del frontend); "
                "solo el backend se deploya."
            )
        parts.append(f"- Modo: {self.mode}")
        return "\n".join(parts)

    def _is_build_cmd(self, args: dict) -> bool:
        cmd = args.get("command", "").strip()
        # Normalizar whitespace para capturar redirects y flags
        cmd = re.sub(r'\s+', ' ', cmd)

        # npm/pnpm/yarn run build (y variantes build:*)
        if re.search(
            r'\b(?:npm run|pnpm(?: run)?|yarn(?: run)?)\s+\S*build\b',
            cmd, re.IGNORECASE
        ):
            return True
        # npx <tool> build — atrapa npx vite build, npx svelte-kit build, etc
        if re.search(r'\bnpx\s+.*?\bbuild\b', cmd, re.IGNORECASE):
            return True
        # cargo/go/uv build
        if re.search(r'\b(?:cargo|go|uv)\s+build\b', cmd, re.IGNORECASE):
            return True
        # node script que involucre build (vite, svelte-kit, esbuild, webpack)
        if re.search(
            r'\bnode\s+.*?\b(?:vite\s+build|svelte-kit\s+build|build\.(?:js|ts)|esbuild|webpack)\b',
            cmd, re.IGNORECASE
        ):
            return True
        return False
