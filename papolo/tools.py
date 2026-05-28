import os
import subprocess
from pathlib import Path

# Env vars que el shell tool puede ver. Cualquier otra cosa
# (especialmente secrets: tokens GitHub, Coolify, Discord, DeepSeek) se filtra
# para que un prompt injection no pueda exfiltrarlos.
_SHELL_ENV_ALLOW = {
    "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "TZ", "PWD", "HOSTNAME",
    "NODE_ENV", "NPM_CONFIG_CACHE", "PNPM_HOME",
    "CARGO_HOME", "RUSTUP_HOME",
    "UV_CACHE_DIR", "PIP_CACHE_DIR",
    "PAPOLO_WORKSPACE_ROOT",
}
_SHELL_ENV_BLOCK_PREFIXES = (
    "PAPOLO_GITHUB_", "COOLIFY_", "DISCORD_", "DEEPSEEK_",
    "OPENAI_", "ANTHROPIC_",
)


def _safe_shell_env() -> dict:
    out = {}
    for k, v in os.environ.items():
        if any(k.startswith(p) for p in _SHELL_ENV_BLOCK_PREFIXES):
            continue
        if k in _SHELL_ENV_ALLOW or k.startswith(("XDG_", "GIT_")):
            out[k] = v
    return out

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo de texto. Devuelve el contenido completo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escribe contenido en un archivo, sobreescribiendo si existe. Crea directorios padre si hace falta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista el contenido de un directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del directorio (default '.')"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Ejecuta un comando de shell y devuelve stdout/stderr/exit code. Usar con cuidado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "description": "Working directory opcional"},
                },
                "required": ["command"],
            },
        },
    },
]


def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {path}"


def list_dir(path: str = ".") -> str:
    entries = []
    for p in sorted(Path(path).iterdir()):
        kind = "dir" if p.is_dir() else "file"
        entries.append(f"[{kind}] {p.name}")
    return "\n".join(entries) or "(empty)"


def shell(command: str, cwd: str | None = None) -> str:
    r = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
        env=_safe_shell_env(),
    )
    return f"exit_code: {r.returncode}\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"


DISPATCH = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "shell": shell,
}
