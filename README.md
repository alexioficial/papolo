# Papolo

Agente con la API de DeepSeek + subagentes + skills. Uso por terminal.

## Instalar
```powershell
cd papolo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
# editar .env y poner DEEPSEEK_API_KEY
```

## Correr
```powershell
papolo
```
o
```powershell
python -m papolo.cli
```

## Estructura
```
papolo/
├── pyproject.toml
├── .env.example
├── papolo/              # paquete python (motor)
│   ├── agent.py         # loop principal con tool use
│   ├── deepseek.py      # cliente API (OpenAI-compat)
│   ├── tools.py         # read_file, write_file, list_dir, shell
│   ├── skills.py        # carga de skills
│   ├── subagents.py     # spawn de subagentes
│   └── cli.py           # entry point terminal
├── subagents/
│   └── _TEMPLATE.md     # template para crear subagentes
└── skills/
    └── _TEMPLATE/SKILL.md  # template para crear skills
```

## Crear un subagente
Copia `subagents/_TEMPLATE.md` a `subagents/<nombre>.md` y completa el frontmatter + cuerpo. El agente principal lo va a ver y puede llamarlo con `spawn_subagent`.

## Crear una skill
Copia `skills/_TEMPLATE/` a `skills/<nombre>/`, edita `SKILL.md`. La skill se carga bajo demanda con la tool `load_skill`.
