---
name: git-workflow
description: Como usar git en el workspace para hacer cambios seguros, branchear experimentos, y revertir cuando algo sale mal. Cargala antes de cualquier modificacion no trivial — el workspace ya tiene `git init` hecho, asi que tenes commits/branches/reset disponibles aunque no haya remote.
---

# Skill: git-workflow

## Cuando usarla
- Vas a hacer cambios en multiples archivos
- Vas a refactorizar algo que podria romper
- Vas a probar un enfoque que quizas haya que descartar
- El usuario te pide "hace X" y X tiene riesgo de regresion
- Estas debugueando y queres bisectar

## Cuando NO usarla
- Un solo archivo, cambio trivial (un typo, agregar un import) — commit no aporta
- Estas solo leyendo / explorando (no hay diffs)
- El usuario explicitamente dijo "no commitees nada"

## Procedimiento

### Checkpoint antes de tocar
```bash
git status                              # ver si hay cambios pendientes
git add -A && git commit -m "checkpoint antes de <tarea>" --allow-empty
```
Si ya hay cambios sucios, primero entender si son tuyos o del usuario.

### Para experimentos riesgosos: branch
```bash
git checkout -b try/<nombre-corto>
# ... trabajas ...
# si sale bien:
git checkout main && git merge try/<nombre-corto>
# si sale mal:
git checkout main && git branch -D try/<nombre-corto>
```

### Commits chicos y descriptivos
Despues de cada subtarea coherente:
```bash
git add <archivos-especificos>          # preferis sobre `git add -A` si hay ruido
git commit -m "<verbo presente>: <que cambio>"
```
Mensajes en imperativo, 50 chars o menos en el subject. Ej: `add user auth endpoint`, no `added user auth endpoint`.

### Revertir el ultimo cambio
```bash
git reset --hard HEAD~1                 # descarta el ultimo commit y sus cambios
git revert HEAD                         # crea commit inverso (no destructivo)
```
`reset --hard` solo si estas seguro de descartar. `revert` es mas seguro.

### Ver que pasó
```bash
git log --oneline -10                   # historial corto
git diff HEAD~1                         # diff del ultimo commit
git show HEAD                           # commit completo
```

### Si te perdiste
```bash
git reflog                              # log de TODOS los movimientos de HEAD
git reset --hard <sha-del-reflog>       # volver a cualquier punto
```
El reflog te salva incluso de `reset --hard` accidentales (90 dias de retencion).

## Reglas del workspace de Papolo
- Cada conversacion tiene su propio repo aislado. No hay remote — todo es local.
- No corras `git push` ni `git pull`: no hay donde.
- No corras `git clean -fdx` salvo que el usuario lo pida explicito.
- Si el usuario quiere ver el diff de algo que hiciste hace 3 pasos, `git diff HEAD~3 HEAD -- <path>`.

## Ejemplos

**Input:** "refactoreame el modulo de auth para que use JWT en vez de sessions"
**Accion:**
1. `git status` → limpio
2. `git checkout -b refactor/jwt-auth`
3. Hacer cambios en `auth/`, `middleware/`, tests
4. `git add auth/ middleware/ tests/auth_test.py && git commit -m "swap session auth for JWT"`
5. Correr tests
6. Si pasan: merge a main. Si no: `git reset --hard HEAD~1` y revisar.

**Input:** "cambia esta linea, dice 'usuarios' y deberia decir 'users'"
**Accion:** Edit directo. No vale la pena commitear un typo (a menos que el usuario lo pida).
