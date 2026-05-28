---
name: debugging-systematic
description: Metodologia para debuggear un bug reportado — reproducir, aislar, formar hipotesis, validar con minimo cambio, fijar la causa raiz. Cargala cuando el usuario reporta "no anda", "falla", "tira error", "se comporta raro", o cuando un test rompe sin causa obvia.
---

# Skill: debugging-systematic

## Cuando usarla
- El usuario reporta un bug o comportamiento inesperado
- Un test que antes pasaba ahora falla
- Un endpoint devuelve 500 / un componente no renderiza / un proceso crashea
- Un comportamiento depende del entorno (anda local, falla en prod)

## Cuando NO usarla
- Es un bug obvio de 1 linea (typo en variable, off-by-one visible). Arreglalo directo.
- Es una feature nueva — no es debugging, es construccion. Usa planner o el subagente del stack.

## Procedimiento

### 1. Reproducir antes de arreglar
- ¿Cual es el input minimo que dispara el bug?
- ¿Es deterministico o intermitente?
- Si no podes reproducir, NO empiezes a cambiar codigo. Pedi mas contexto al usuario: logs, stack trace, version, comando exacto.

### 2. Leer el error literal
- Stack trace de arriba abajo: primera linea = sintoma, ultima linea = lugar donde ocurrio.
- Si dice `NoneType has no attribute X` → algo que esperabas no-None vino None. Rastreá *donde* se hace None.
- No saltes a soluciones. Leelo entero.

### 3. Bisectar
- Si hay commits sospechosos: `git log --oneline` y `git bisect start / bad / good <sha>` para encontrar el commit que rompio.
- Si no hay history util: comenta mitad del codigo afectado y ve si el bug desaparece. Despues mitad de esa mitad.

### 4. Hipotesis → test
- Formula UNA hipotesis: "creo que falla porque X esta nil cuando el path Y se ejecuta antes de Z".
- Validala con el cambio mas chico posible: un `print`/`log`, un test que reproduzca, un assert.
- No cambies multiples cosas a la vez. Si arreglas 3 cosas y funciona, no sabes cual era el bug.

### 5. Fijar la causa raiz, no el sintoma
- Si pones `if x is None: return` y el bug desaparece, preguntate *por que* x era None. Esa es la causa.
- Sintomas comunes que tapan causas raiz:
  - `try/except` que swallowea
  - default values que ocultan inicializacion faltante
  - retries que esconden races
- A veces el fix correcto ES manejar el caso edge. Pero confirmalo, no asumas.

### 6. Test de regresion
- Antes de cerrar, escribi un test que falle SIN tu fix y pase CON tu fix. Asi nadie reintroduce el bug.

### 7. Revertir lo que no aporto
- Si en el camino agregaste prints/logs/comments, sacalos antes de commitear.
- `git diff` final debe contener SOLO el fix + el test.

## Trampas a evitar
- **"Funciona en mi maquina"**: si solo prueba con tus datos, no probo. Pedi el caso del usuario.
- **Shotgun debugging**: cambiar 5 cosas y ver si arregla. No aprendes nada.
- **Cargo cult**: copiar un fix de stack overflow sin entender por que funciona.
- **Heisenbugs**: agregar logging que "cambia el timing" y el bug desaparece — sospecha race condition.

## Ejemplos

**Input:** "el endpoint /users/{id} tira 500"
**Accion:**
1. Pedir el id exacto que falla, o el stack trace
2. `curl localhost:8000/users/<id>` para reproducir
3. Leer stack trace → `KeyError: 'email'` en `serializer.py:42`
4. Hipotesis: hay usuarios sin email en DB
5. `SELECT id FROM users WHERE email IS NULL LIMIT 5;` → confirmado
6. Decision: ¿es valido tener email NULL? Si si, schema debe tolerarlo (`Optional[str]`). Si no, fix es backfill + NOT NULL constraint.
7. Test que llame al endpoint con un user sin email y verifique el comportamiento elegido.

**Input:** "el test test_auth_login a veces falla"
**Accion:** Intermitente = race condition probable. Buscar:
- Estado compartido entre tests (DB no limpia, singleton)
- Tiempo (timestamps, `now()`, timeouts cortos)
- Orden de tests (`pytest --randomly` para forzarlo)
