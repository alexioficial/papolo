---
name: refactoring-safely
description: Como refactorizar codigo sin romperlo — pasos pequenios, checkpoints en git, tests primero, separar cambio de comportamiento de cambio de estructura. Cargala cuando el usuario pide "limpia esto", "extrae X", "renombra Y", o cuando el codigo necesita reorganizarse antes de agregar features.
---

# Skill: refactoring-safely

## Cuando usarla
- "Limpia / mejora / ordena esto"
- "Extrae esta funcion / componente / modulo"
- "Renombra X a Y"
- "Esto esta acoplado, separalo"
- Antes de agregar una feature grande sobre codigo viejo

## Cuando NO usarla
- Rewrite from scratch — no es refactor, es proyecto nuevo
- Cambio de comportamiento (no es refactor por definicion)
- Cambio trivial (renombrar una variable en un archivo)

## Definicion estricta
Refactor = cambiar la **estructura** del codigo SIN cambiar su **comportamiento observable**. Si hay tests, deben seguir pasando sin modificar. Si cambias tests, ya no es refactor puro.

## Procedimiento

### 1. Asegurar safety net
- ¿Hay tests que cubran el codigo a refactorizar?
- Si NO: escribilos *antes* de refactorizar. Aunque sean tests de caracterizacion (capturan el comportamiento actual, no juzgan si es correcto).
- Correlos y verifica que pasan en verde.

### 2. Checkpoint en git
```bash
git add -A && git commit -m "checkpoint: pre-refactor de <area>"
```
Asi `git reset --hard HEAD` o `HEAD~1` siempre te trae de vuelta.

### 3. Refactorear en pasos chicos
Cada paso:
1. Hacer UN cambio pequenio (extraer una funcion, renombrar una variable)
2. Correr tests
3. Si pasan: commit
4. Si fallan: revertir o arreglar antes de seguir

NUNCA hagas 5 cambios y despues corras tests. Si falla, no sabes cual rompio.

### 4. Refactors comunes y como hacerlos

#### Extract function
1. Identificar el bloque a extraer
2. Listar variables que entran (parametros) y salen (return)
3. Crear la funcion nueva con esa signature, copiando el cuerpo
4. Reemplazar el bloque por la llamada
5. Correr tests

#### Rename
- Usa la herramienta del lenguaje (LSP rename) si la tenes
- Si no: `grep` el nombre viejo, asegurate que sean usos del mismo simbolo (no falsos positivos en strings/docs)
- Cambia y corre tests

#### Move function/class entre archivos
1. Crear el archivo destino vacio si no existe
2. Mover la definicion (cortar y pegar)
3. Agregar el import en el archivo origen
4. Re-correr tests
5. Eliminar imports muertos del archivo origen

#### Split modulo grande
- Identifica cohesiones internas (que cosas se usan juntas)
- Extrae UN concepto a la vez a un sub-modulo
- Re-exporta desde el modulo original para no romper imports externos
- En commits posteriores, actualizar imports externos uno por uno

### 5. Separar refactor de feature
Si vas a agregar X feature pero antes hay que limpiar:
1. **PR/commit 1**: solo refactor, tests siguen pasando, cero cambio de comportamiento
2. **PR/commit 2**: feature nueva sobre el codigo ya limpio

Mezclar refactor + feature en el mismo diff hace imposible revisar y rollback.

## Smells que sugieren refactor
- Funciones de >50 lineas o >3 niveles de indentacion
- Mismo bloque copy-pasted en 3+ lugares
- Parametros que siempre vienen juntos (sugiere struct/object)
- Nombres genericos: `data`, `result`, `manager`, `helper`
- Comentarios que explican QUE hace el codigo (en vez de POR QUE) → el codigo no es claro
- Tests dificiles de escribir → diseno acoplado

## NO refactores
- Codigo que esta a punto de ser borrado
- Codigo que funciona y no vas a tocar de nuevo
- Por "limpieza estetica" sin valor concreto — tiempo perdido y diff que revisar

## Ejemplo

**Input:** "extrae la validacion de email del handler a una funcion"

**Accion:**
1. `git status` → limpio. `git log` → tests verdes.
2. Identificar bloque en `handlers.py`:
   ```python
   if "@" not in email or len(email) > 254:
       raise HTTPException(400, "invalid email")
   ```
3. Crear `validators.py`:
   ```python
   def validate_email(email: str) -> None:
       if "@" not in email or len(email) > 254:
           raise ValueError("invalid email")
   ```
4. En handler:
   ```python
   try: validate_email(email)
   except ValueError as e: raise HTTPException(400, str(e))
   ```
5. Correr tests. Verde.
6. `git add validators.py handlers.py && git commit -m "extract validate_email from handler"`
7. (Opcional) test unitario directo de `validate_email`.
