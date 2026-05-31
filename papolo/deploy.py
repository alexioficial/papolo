"""
Tools de deploy: GitHub repo creation/push, Coolify app create/deploy/status.

Las tools se exponen al modelo SOLO si las env vars correspondientes estan seteadas
(feature flag implicito). Los tokens NUNCA se pasan al modelo: las tools los leen
del environment del proceso bot, no de los args.

El modulo expone callbacks opcionales:
  - set_db_callback(cb): para persistir eventos (repo_created, app_created, etc)
  - set_confirmation_callback(cb): para ops destructivas via Discord
"""

import json
import os
import re
import subprocess

try:
    import requests
except ImportError:
    requests = None


def _env(k: str) -> str | None:
    return os.environ.get(k)


def _required(*keys: str) -> bool:
    return all(_env(k) for k in keys)


GITHUB_ENABLED = _required("PAPOLO_GITHUB_PAT", "PAPOLO_GITHUB_USER") and requests is not None
COOLIFY_ENABLED = _required(
    "COOLIFY_BASE_URL", "COOLIFY_API_TOKEN",
    "COOLIFY_SERVER_UUID", "COOLIFY_PROJECT_UUID",
    "PAPOLO_PREVIEW_DOMAIN",
) and requests is not None


# --- Callbacks inyectados por el bot ---

_db_cb = None
_confirm_cb = None


def set_db_callback(cb):
    """cb(event: str, payload: dict) -> Any. Llamado en eventos de deploy."""
    global _db_cb
    _db_cb = cb


def set_confirmation_callback(cb):
    """
    cb(conversation_uuid, action, target, confirm_token) -> tuple

    Devuelve:
      ('PENDING', mensaje)  si confirm_token == 'ASK' y se posteo pedido al user
      ('OK', token)         si confirm_token es valido y fue consumido
      ('INVALID', razon)    si confirm_token no es valido
    """
    global _confirm_cb
    _confirm_cb = cb


def _emit(event: str, payload: dict):
    if _db_cb:
        try:
            return _db_cb(event, payload)
        except Exception as e:
            return f"db_cb error: {e}"
    return None


# --- Helpers ---

def _short(conversation_uuid: str) -> str:
    return (conversation_uuid or "anon").split("-")[0][:8]


def _safe_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", (name or "app").strip().lower())
    s = s[:50].strip("-")
    return s or "app"


def _gh_headers():
    return {
        "Authorization": f"Bearer {_env('PAPOLO_GITHUB_PAT')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _cf_headers():
    return {
        "Authorization": f"Bearer {_env('COOLIFY_API_TOKEN')}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _cf_url(path: str) -> str:
    return f"{_env('COOLIFY_BASE_URL').rstrip('/')}{path}"


def _mask_pat(text: str) -> str:
    pat = _env("PAPOLO_GITHUB_PAT") or ""
    if pat and pat in text:
        text = text.replace(pat, "***")
    return re.sub(r"x-access-token:[^@]+@", "x-access-token:***@", text)


# --- Tools GitHub ---

def github_create_repo(*, workspace_dir, conversation_uuid,
                        name, description="", private=False):
    if not GITHUB_ENABLED:
        return "ERROR: integracion GitHub no configurada"
    if _db_cb:
        try:
            count = _db_cb("count_repos", {"conversation_uuid": conversation_uuid})
            if isinstance(count, int) and count >= 5:
                return "ERROR: limite de 5 repos por conversacion alcanzado"
        except Exception:
            pass
    safe = _safe_name(name)
    short = _short(conversation_uuid)
    repo_name = f"papolo-{short}-{safe}"
    body = {
        "name": repo_name,
        "description": (description or "")[:300],
        "private": bool(private),
        "auto_init": False,
    }
    r = requests.post("https://api.github.com/user/repos",
                       json=body, headers=_gh_headers(), timeout=20)
    if r.status_code >= 300:
        return f"ERROR github ({r.status_code}): {r.text[:300]}"
    data = r.json()
    html_url = data["html_url"]
    clone_url = data["clone_url"]
    _emit("repo_created", {
        "conversation_uuid": conversation_uuid,
        "github_repo_name": repo_name,
        "github_repo_url": html_url,
    })
    return (
        f"OK repo creado.\n"
        f"name: {repo_name}\n"
        f"html_url: {html_url}\n"
        f"clone_url: {clone_url}"
    )


def github_push_workspace(*, workspace_dir, conversation_uuid,
                           repo_url, commit_message="deploy"):
    if not GITHUB_ENABLED:
        return "ERROR: integracion GitHub no configurada"
    if not workspace_dir:
        return "ERROR: sin workspace_dir"
    pat = _env("PAPOLO_GITHUB_PAT")
    auth_url = re.sub(r"^https://", f"https://x-access-token:{pat}@", repo_url)
    script = (
        f'set -e\n'
        f'cd "{workspace_dir}"\n'
        f'git add -A\n'
        f'git commit -m {json.dumps(commit_message)} --allow-empty -q\n'
        f'git remote remove origin 2>/dev/null || true\n'
        f'git remote add origin "{auth_url}"\n'
        f'git branch -M main\n'
        f'git push -u origin main\n'
    )
    try:
        r = subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: push timeout (120s)"
    except FileNotFoundError:
        return "ERROR: bash no encontrado en el sistema"
    out = _mask_pat(r.stdout + "\n" + r.stderr)
    if r.returncode != 0:
        return f"ERROR push (exit {r.returncode}):\n{out}"
    return f"OK push:\n{out}"


def github_delete_repo(*, workspace_dir, conversation_uuid,
                        repo_name, confirm_token="ASK"):
    if not GITHUB_ENABLED:
        return "ERROR: integracion GitHub no configurada"
    if not _confirm_cb:
        return "ERROR: confirmation callback no registrado"
    decision = _confirm_cb(conversation_uuid, "delete_repo", repo_name, confirm_token)
    if decision[0] == "PENDING":
        return f"PENDING_CONFIRMATION: {decision[1]}"
    if decision[0] != "OK":
        return f"ERROR confirmacion: {decision[1]}"
    user = _env("PAPOLO_GITHUB_USER")
    r = requests.delete(
        f"https://api.github.com/repos/{user}/{repo_name}",
        headers=_gh_headers(), timeout=20,
    )
    if r.status_code >= 300:
        return f"ERROR delete repo ({r.status_code}): {r.text[:300]}"
    _emit("repo_deleted", {
        "conversation_uuid": conversation_uuid,
        "github_repo_name": repo_name,
    })
    return f"OK repo borrado: {repo_name}"


# --- Tools Coolify ---

def coolify_create_app(*, workspace_dir, conversation_uuid,
                        repo_url, branch="main", port=3000,
                        build_pack="nixpacks", subdomain=None):
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    sub = subdomain or _short(conversation_uuid)
    fqdn = f"https://{sub}.{_env('PAPOLO_PREVIEW_DOMAIN')}"
    body = {
        "project_uuid": _env("COOLIFY_PROJECT_UUID"),
        "server_uuid": _env("COOLIFY_SERVER_UUID"),
        "environment_name": "production",
        "git_repository": repo_url,
        "git_branch": branch,
        "build_pack": build_pack,
        "ports_exposes": str(port),
        "domains": fqdn,
        "instant_deploy": False,
    }
    r = requests.post(_cf_url("/api/v1/applications/public"),
                       json=body, headers=_cf_headers(), timeout=30)
    if r.status_code >= 300:
        return f"ERROR coolify create ({r.status_code}): {r.text[:500]}"
    data = r.json()
    app_uuid = data.get("uuid") or (data.get("data") or {}).get("uuid")
    if not app_uuid:
        return f"ERROR coolify: respuesta sin uuid:\n{json.dumps(data)[:500]}"
    _emit("app_created", {
        "conversation_uuid": conversation_uuid,
        "coolify_app_uuid": app_uuid,
        "preview_url": fqdn,
    })
    return f"OK app creada.\nuuid: {app_uuid}\npreview_url: {fqdn}"


def _coolify_upsert_env(app_uuid: str, key: str, value: str) -> tuple[int, str]:
    """POST crea env; si ya existe (4xx por duplicate), hace PATCH al endpoint by-key."""
    body = {"key": key, "value": value}
    r = requests.post(_cf_url(f"/api/v1/applications/{app_uuid}/envs"),
                       json=body, headers=_cf_headers(), timeout=20)
    if r.status_code < 300:
        return r.status_code, r.text
    if r.status_code in (400, 409, 422) and ("exist" in r.text.lower() or "duplicate" in r.text.lower()):
        r2 = requests.patch(_cf_url(f"/api/v1/applications/{app_uuid}/envs"),
                             json=body, headers=_cf_headers(), timeout=20)
        return r2.status_code, r2.text
    return r.status_code, r.text


def coolify_set_mongodb_env(*, workspace_dir, conversation_uuid, app_uuid):
    """Setea MONGODB_URI en la app Coolify usando el URI del env del bot.
    El valor NUNCA pasa por el modelo — se lee de PAPOLO_MONGODB_URI."""
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    uri = _env("PAPOLO_MONGODB_URI")
    if not uri:
        return "ERROR: PAPOLO_MONGODB_URI no esta configurado en el bot"
    code, text = _coolify_upsert_env(app_uuid, "MONGODB_URI", uri)
    if code >= 300:
        return f"ERROR coolify env ({code}): {text[:300]}"
    return "OK MONGODB_URI inyectado en la app (valor oculto). Acordate de coolify_deploy para que tome el cambio."


def coolify_set_env(*, workspace_dir, conversation_uuid,
                     app_uuid, key, value):
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    code, text = _coolify_upsert_env(app_uuid, key, value)
    if code >= 300:
        return f"ERROR coolify env ({code}): {text[:300]}"
    return f"OK env seteado: {key}. Acordate de coolify_deploy para que tome el cambio."


def coolify_update_app(*, workspace_dir, conversation_uuid,
                        app_uuid, port=None, branch=None, build_pack=None):
    """Actualiza campos de una app Coolify existente. Util para cambiar puerto o
    branch sin destruir/recrear. PATCH a /api/v1/applications/{uuid}."""
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    body: dict = {}
    if port is not None:
        body["ports_exposes"] = str(port)
    if branch is not None:
        body["git_branch"] = branch
    if build_pack is not None:
        body["build_pack"] = build_pack
    if not body:
        return "ERROR: nada para actualizar (pasa al menos uno de port/branch/build_pack)"
    r = requests.patch(_cf_url(f"/api/v1/applications/{app_uuid}"),
                        json=body, headers=_cf_headers(), timeout=20)
    if r.status_code >= 300:
        return f"ERROR coolify update ({r.status_code}): {r.text[:300]}"
    return f"OK app actualizada: {', '.join(body.keys())}. Acordate de coolify_deploy para que tome el cambio."


def coolify_deploy(*, workspace_dir, conversation_uuid, app_uuid):
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    r = requests.post(_cf_url(f"/api/v1/applications/{app_uuid}/start"),
                       headers=_cf_headers(), timeout=30)
    if r.status_code >= 300:
        return f"ERROR coolify deploy ({r.status_code}): {r.text[:300]}"
    _emit("deploy_triggered", {
        "conversation_uuid": conversation_uuid,
        "coolify_app_uuid": app_uuid,
    })
    return f"OK deploy disparado.\n{r.text[:400]}"


_STATUS_USEFUL_KEYS = (
    "uuid", "name", "status", "fqdn", "build_pack", "ports_exposes",
    "git_repository", "git_branch", "git_commit_sha",
    "updated_at", "last_online_at", "config_hash",
)


def coolify_status(*, workspace_dir, conversation_uuid, app_uuid):
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    r = requests.get(_cf_url(f"/api/v1/applications/{app_uuid}"),
                      headers=_cf_headers(), timeout=20)
    if r.status_code >= 300:
        return f"ERROR coolify status ({r.status_code}): {r.text[:300]}"
    data = r.json()
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    status = inner.get("status") or "unknown"
    fqdn = inner.get("fqdn") or ""
    slim = {k: inner.get(k) for k in _STATUS_USEFUL_KEYS if inner.get(k) is not None}
    hint = ""
    if status.startswith("running"):
        hint = "\nHINT: status empieza con 'running' → la app esta arriba. Reporta el URL al usuario y termina la tarea. No hagas mas tools."
    elif status.startswith("exited") or status.startswith("failed"):
        hint = "\nHINT: deploy fallo. Lee build/runtime logs (la API no los expone directo — fixea desde codigo o config y haz coolify_deploy denuevo). NO destruyas la app."
    return (
        f"status: {status}\n"
        f"fqdn: {fqdn}\n"
        f"--- summary ---\n{json.dumps(slim)}"
        f"{hint}"
    )


def coolify_destroy_app(*, workspace_dir, conversation_uuid,
                         app_uuid, confirm_token="ASK"):
    if not COOLIFY_ENABLED:
        return "ERROR: integracion Coolify no configurada"
    if not _confirm_cb:
        return "ERROR: confirmation callback no registrado"
    decision = _confirm_cb(conversation_uuid, "destroy_app", app_uuid, confirm_token)
    if decision[0] == "PENDING":
        return f"PENDING_CONFIRMATION: {decision[1]}"
    if decision[0] != "OK":
        return f"ERROR confirmacion: {decision[1]}"
    r = requests.delete(_cf_url(f"/api/v1/applications/{app_uuid}"),
                         headers=_cf_headers(), timeout=30)
    if r.status_code >= 300:
        return f"ERROR destroy app ({r.status_code}): {r.text[:300]}"
    _emit("app_destroyed", {
        "conversation_uuid": conversation_uuid,
        "coolify_app_uuid": app_uuid,
    })
    return f"OK app destruida: {app_uuid}"


# --- Schemas registrados condicionalmente ---

_SCHEMAS_GITHUB = [
    {"type": "function", "function": {
        "name": "github_create_repo",
        "description": (
            "Crea un repo en GitHub bajo la cuenta del usuario. El nombre real sera "
            "'papolo-<short-uuid>-<name>' (prefix forzado). Devuelve clone_url y html_url. "
            "Limite: 5 repos por conversacion."
        ),
        "parameters": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "description": "sufijo descriptivo (a-z, 0-9, -)"},
            "description": {"type": "string"},
            "private": {"type": "boolean", "description": "default false"},
        }},
    }},
    {"type": "function", "function": {
        "name": "github_push_workspace",
        "description": (
            "Pushea el contenido del workspace al repo. Agrega-commitea-pushea a main. "
            "El PAT se inyecta internamente (no lo manejas vos)."
        ),
        "parameters": {"type": "object", "required": ["repo_url"], "properties": {
            "repo_url": {"type": "string", "description": "html_url o clone_url del repo"},
            "commit_message": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "github_delete_repo",
        "description": (
            "Borra un repo de GitHub. REQUIERE confirmacion del usuario. "
            "Primero llamala con confirm_token='ASK' — el bot le va a preguntar al "
            "usuario en el thread y va a esperar su respuesta. Cuando el usuario "
            "responda con el token de confirmacion, lo vas a recibir como mensaje "
            "del usuario y vas a llamar esta tool de nuevo con ese token."
        ),
        "parameters": {"type": "object", "required": ["repo_name"], "properties": {
            "repo_name": {"type": "string", "description": "nombre exacto 'papolo-XXXX-...'"},
            "confirm_token": {"type": "string", "description": "'ASK' o el codigo del usuario"},
        }},
    }},
]

_SCHEMAS_COOLIFY = [
    {"type": "function", "function": {
        "name": "coolify_create_app",
        "description": (
            "Crea una application en Coolify desde un repo publico. Default port 3000, "
            "build_pack 'nixpacks' (autodetecta sveltekit/fastapi/etc). El subdomain "
            "default es los primeros 8 chars del conversation uuid."
        ),
        "parameters": {"type": "object", "required": ["repo_url"], "properties": {
            "repo_url": {"type": "string"},
            "branch": {"type": "string", "description": "default 'main'"},
            "port": {"type": "integer", "description": "default 3000"},
            "build_pack": {"type": "string", "description": "nixpacks | static | dockerfile"},
            "subdomain": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_set_env",
        "description": (
            "Setea una variable de entorno (runtime) en una app Coolify. "
            "Si la key ya existe, hace upsert. Despues llama coolify_deploy "
            "para que el container la tome."
        ),
        "parameters": {"type": "object", "required": ["app_uuid", "key", "value"], "properties": {
            "app_uuid": {"type": "string"},
            "key": {"type": "string"},
            "value": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_update_app",
        "description": (
            "Actualiza una app Coolify existente sin destruirla. Util cuando "
            "tenes que cambiar el puerto, el branch git, o el build_pack despues "
            "de crear la app. Despues llama coolify_deploy."
        ),
        "parameters": {"type": "object", "required": ["app_uuid"], "properties": {
            "app_uuid": {"type": "string"},
            "port": {"type": "integer", "description": "nuevo ports_exposes"},
            "branch": {"type": "string", "description": "nuevo git_branch"},
            "build_pack": {"type": "string", "description": "nixpacks | static | dockerfile"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_set_mongodb_env",
        "description": (
            "Inyecta MONGODB_URI en la app Coolify. El valor se toma del env "
            "del bot (PAPOLO_MONGODB_URI) — vos NO pasas el URI ni lo conoces. "
            "Usar antes de coolify_deploy en apps que necesitan Mongo."
        ),
        "parameters": {"type": "object", "required": ["app_uuid"], "properties": {
            "app_uuid": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_deploy",
        "description": "Dispara un deploy de la app. Usar despues de coolify_create_app o despues de cambiar envs.",
        "parameters": {"type": "object", "required": ["app_uuid"], "properties": {
            "app_uuid": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_status",
        "description": (
            "Devuelve el status actual de la app. Llamala en loop con sleeps "
            "(via shell 'sleep 10') hasta que status sea 'running' o 'failed'."
        ),
        "parameters": {"type": "object", "required": ["app_uuid"], "properties": {
            "app_uuid": {"type": "string"},
        }},
    }},
    {"type": "function", "function": {
        "name": "coolify_destroy_app",
        "description": (
            "Destruye una app Coolify. REQUIERE confirmacion del usuario "
            "(mismo flujo que github_delete_repo)."
        ),
        "parameters": {"type": "object", "required": ["app_uuid"], "properties": {
            "app_uuid": {"type": "string"},
            "confirm_token": {"type": "string"},
        }},
    }},
]

DEPLOY_TOOL_SCHEMAS: list = []
if GITHUB_ENABLED:
    DEPLOY_TOOL_SCHEMAS += _SCHEMAS_GITHUB
if COOLIFY_ENABLED:
    DEPLOY_TOOL_SCHEMAS += _SCHEMAS_COOLIFY

DEPLOY_DISPATCH: dict = {}
if GITHUB_ENABLED:
    DEPLOY_DISPATCH.update({
        "github_create_repo": github_create_repo,
        "github_push_workspace": github_push_workspace,
        "github_delete_repo": github_delete_repo,
    })
if COOLIFY_ENABLED:
    DEPLOY_DISPATCH.update({
        "coolify_create_app": coolify_create_app,
        "coolify_set_env": coolify_set_env,
        "coolify_set_mongodb_env": coolify_set_mongodb_env,
        "coolify_update_app": coolify_update_app,
        "coolify_deploy": coolify_deploy,
        "coolify_status": coolify_status,
        "coolify_destroy_app": coolify_destroy_app,
    })


def deploy_index_for_prompt() -> str:
    """Resumen de capacidades de deploy para el system prompt."""
    parts = []
    if GITHUB_ENABLED:
        parts.append(
            "GitHub: podes crear repos (github_create_repo), pushear el workspace "
            "(github_push_workspace) y borrar repos con confirmacion (github_delete_repo). "
            "El PAT se maneja internamente, vos NO tenes acceso directo."
        )
    if COOLIFY_ENABLED:
        parts.append(
            "Coolify: podes crear apps (coolify_create_app), setear envs "
            "(coolify_set_env, coolify_set_mongodb_env), actualizar port/branch/buildpack "
            "de una app existente (coolify_update_app), deployar (coolify_deploy), "
            "monitorear (coolify_status) y destruir con confirmacion (coolify_destroy_app). "
            f"Las previews quedan en https://<short>.{_env('PAPOLO_PREVIEW_DOMAIN')}."
        )
    if not parts:
        return ""
    return (
        "Capacidades de deploy disponibles:\n- "
        + "\n- ".join(parts)
        + "\nReglas criticas de deploy (no negociables):\n"
        + "- ANTES de tu primer coolify_create_app: SIEMPRE carga la skill 'coolify-deploy' con load_skill. Ahi estan los templates de Dockerfile por stack y el procedimiento exacto.\n"
        + "- Para CUALQUIER stack, siempre build_pack=\"dockerfile\". Nunca nixpacks, nunca docker-compose. Escribi un Dockerfile a mano en el workspace.\n"
        + "- Cuando coolify_status devuelva status que empiece con 'running' (incluyendo 'running:unknown'): PARA. Reporta el preview URL al usuario y termina la tarea. NO destruyas ni reescribas la app.\n"
        + "- coolify_destroy_app solo se usa si el usuario lo pide explicitamente. Un deploy fallido NO es razon para destruir — fixea y haz coolify_deploy denuevo.\n"
        + "- Para cambiar puerto/branch/buildpack de una app existente usa coolify_update_app — NUNCA destruyas y recrees.\n"
        + "- Despues de coolify_set_env o coolify_set_mongodb_env o coolify_update_app, llama coolify_deploy para que el container tome los cambios."
    )
