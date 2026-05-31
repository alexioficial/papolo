from pathlib import Path
import yaml

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _fallback_parse(raw: str) -> dict:
    """Parser simple para frontmatter cuando YAML tira ScannerError.
    Toma cada linea `key: value` como entry. No soporta nested ni listas."""
    meta: dict = {}
    for line in raw.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        meta[key] = value
    return meta


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            meta = _fallback_parse(raw)
    except yaml.YAMLError:
        meta = _fallback_parse(raw)
    return meta, body


def list_skills() -> list[dict]:
    skills = []
    if not SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        meta, _ = _parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        skills.append({
            "name": meta.get("name", skill_dir.name),
            "description": meta.get("description", ""),
            "path": str(skill_md),
        })
    return skills


def load_skill(name: str) -> str | None:
    skill_md = SKILLS_DIR / name / "SKILL.md"
    if not skill_md.exists():
        return None
    return skill_md.read_text(encoding="utf-8")


def skills_index_for_prompt() -> str:
    skills = list_skills()
    if not skills:
        return "(sin skills instaladas)"
    lines = [
        "Skills disponibles. Para activar una, llama a load_skill(name=...):",
    ]
    for s in skills:
        lines.append(f"- {s['name']}: {s['description']}")
    return "\n".join(lines)


SKILL_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "load_skill",
        "description": "Carga el contenido completo de una skill por nombre. Devuelve las instrucciones y procedimiento de esa skill.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre de la skill"}
            },
            "required": ["name"],
        },
    },
}


def skill_tool_dispatch(name: str) -> str:
    content = load_skill(name)
    if content is None:
        return f"Skill '{name}' no encontrada"
    return content
