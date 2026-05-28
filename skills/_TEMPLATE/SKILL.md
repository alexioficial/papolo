---
name: nombre-de-skill
description: Cuando usar esta skill — describe los triggers (que tipo de pedido del usuario la dispara) y el alcance. Esta linea la lee el agente para decidir si cargarla.
---

# Skill: {{nombre}}

## Cuando usarla
{{Lista concreta de situaciones que disparan esta skill. Ej:
- El usuario pide "crear un PR"
- El usuario menciona migraciones de base de datos
- Aparece un error de tipo X
}}

## Cuando NO usarla
{{Casos similares pero que no aplican. Ayuda a desambiguar.}}

## Procedimiento
1. {{Paso concreto}}
2. {{Paso concreto}}
3. {{Paso concreto}}

## Recursos
- `scripts/` — helpers que la skill puede invocar via shell
- `references/` — material de referencia que el agente puede leer con read_file si lo necesita
- `examples/` — ejemplos resueltos

## Ejemplos
**Input:** {{ejemplo de pedido del usuario}}
**Accion:** {{que hace la skill paso a paso}}
**Output:** {{como queda el resultado}}
