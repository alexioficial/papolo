"""
Eleccion de tech stack al inicio de una tarea de programacion.

Modulo neutral (sin dependencias internas, como prompts.py) para evitar imports
circulares: lo importa agent.py.

Flujo: cuando arranca una tarea de programacion NUEVA, el orquestador llama la tool
`ask_tech_stack` como primer paso. Esta invoca un callback que el bot registra
(`set_stack_callback`) para mostrarle al usuario un menu de frontend + backend por
reacciones en Discord y esperar su eleccion. La base de datos SIEMPRE es MongoDB
(no se pregunta). El resultado le dice al modelo que stack eligio el usuario y que
subagente experto usar en cada capa.

En modo CLI / sin callback registrado, cae a un default (SvelteKit fullstack) para
no romper el flujo.
"""

# Opciones que se le ofrecen al usuario. (key interno, etiqueta humana).
FRONTEND_OPTIONS = [
    ("sveltekit", "SvelteKit"),
    ("flutter", "Flutter + Dart"),
    ("react", "React + TypeScript"),
]
BACKEND_OPTIONS = [
    ("fastapi", "Python + FastAPI"),
    ("go-fiber", "Go + Fiber"),
    ("rust-actix", "Rust + Actix Web"),
    ("sveltekit", "SvelteKit (fullstack)"),
]

# key -> subagente experto que construye esa capa.
FRONTEND_EXPERT = {
    "sveltekit": "sveltekit-expert",
    "flutter": "flutter-dart-expert",
    "react": "react-typescript-expert",
}
BACKEND_EXPERT = {
    "fastapi": "fastapi-expert",
    "go-fiber": "golang-fiber-expert",
    "rust-actix": "rust-actix-expert",
    "sveltekit": "sveltekit-expert",
}

_FE_LABEL = dict(FRONTEND_OPTIONS)
_BE_LABEL = dict(BACKEND_OPTIONS)


# --- Callback inyectado por el bot ---

_STACK_CB = None


def set_stack_callback(cb):
    """cb(conversation_uuid, frontend_options, backend_options) -> (frontend_key, backend_key)

    frontend_options / backend_options son las listas de tuplas (key, etiqueta). El
    callback muestra el menu al usuario (reacciones) y devuelve las keys elegidas.
    Bloquea hasta que el usuario elige (o cae a un default tras timeout)."""
    global _STACK_CB
    _STACK_CB = cb


ASK_TECH_STACK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_tech_stack",
        "description": (
            "Le pregunta al usuario que tech stack usar (frontend + backend) mostrando "
            "un menu por reacciones en Discord y espera su eleccion. La base de datos "
            "SIEMPRE es MongoDB (no se pregunta). Llamalo UNA sola vez, como PRIMER "
            "tool_call (solo, sin nada mas), al empezar una tarea de programacion NUEVA. "
            "NO lo llames para preguntas/consultas que no requieren programar, ni para "
            "una tarea ya iniciada donde el stack ya se eligio. Devuelve el stack elegido "
            "y que subagente experto usar en cada capa."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def is_fullstack_sveltekit(frontend: str, backend: str) -> bool:
    """SvelteKit para frontend Y backend = fullstack (adapter-node, un solo deploy)."""
    return frontend == "sveltekit" and backend == "sveltekit"


def ask_tech_stack(conversation_uuid: str | None = None, **_) -> str:
    if _STACK_CB is None:
        # CLI / sin canal interactivo: default razonable sin bloquear.
        return _format(
            "sveltekit", "sveltekit",
            note="(sin canal interactivo para preguntar — usé el default SvelteKit fullstack + MongoDB)",
        )
    try:
        frontend, backend = _STACK_CB(conversation_uuid, FRONTEND_OPTIONS, BACKEND_OPTIONS)
    except Exception as e:
        return (
            f"ERROR pidiendo el stack al usuario: {e}. Elegí vos un default razonable "
            "(SvelteKit fullstack + MongoDB), avisá al usuario que lo asumiste y seguí."
        )
    return _format(frontend, backend)


def _format(frontend: str, backend: str, note: str = "") -> str:
    fe_h = _FE_LABEL.get(frontend, frontend)
    be_h = _BE_LABEL.get(backend, backend)
    lines = ["[STACK ELEGIDO POR EL USUARIO — construí SOLO con esto, no cambies de framework por preferencia propia]"]

    if is_fullstack_sveltekit(frontend, backend):
        lines += [
            "Arquitectura: SvelteKit FULLSTACK (adapter-node, UN solo deploy).",
            f"- Frontend + Backend: {fe_h} → subagente `sveltekit-expert`.",
            "- Server routes (`+page.server.ts`, `+server.ts`) + form actions conectando DIRECTO a MongoDB. NO metas un backend separado.",
            "- Base de datos: MongoDB (siempre). Modelado de datos con el subagente `mongodb-expert`.",
            "Es el flujo fullstack SvelteKit habitual — seguilo tal cual lo venís haciendo.",
        ]
    else:
        fe_exp = FRONTEND_EXPERT.get(frontend, "?")
        be_exp = BACKEND_EXPERT.get(backend, "?")
        lines += [
            "Arquitectura: frontend + backend SEPARADOS (DOS deploys, dos URLs).",
            f"- Frontend: {fe_h} → subagente `{fe_exp}`.",
            f"- Backend: {be_h} → subagente `{be_exp}`.",
            "- Base de datos: MongoDB (siempre), conectada SOLO desde el backend. Modelado con `mongodb-expert`.",
            "- El frontend consume la API del backend por HTTP (configurá CORS + credenciales bien). NUNCA bundlees el frontend adentro del backend.",
        ]
        if frontend == "flutter":
            lines.append(
                "- NOTA Flutter: por ahora solo construí el codigo del cliente con `flutter-dart-expert`. "
                "El pipeline de compilacion/deploy de Flutter TODAVIA no está cableado — no intentes "
                "deployarlo como una web SvelteKit. Dejá la app compilable y avisá al usuario."
            )
        if backend == "sveltekit" and frontend != "sveltekit":
            lines.append(
                "- NOTA: elegiste SvelteKit como backend con otro frontend. Usá `sveltekit-expert` para "
                "exponer una API JSON pura (`+server.ts`) contra Mongo; el frontend la consume por HTTP."
            )

    if note:
        lines.append(note)
    return "\n".join(lines)
