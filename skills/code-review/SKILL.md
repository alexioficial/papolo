---
name: code-review
description: Heuristicas para revisar codigo propio o ajeno antes de marcarlo como hecho — correctitud, seguridad, claridad, tests, performance obvia. Cargala antes de cerrar una tarea no trivial o cuando el usuario pide "revisa esto" / "que opinas del codigo".
---

# Skill: code-review

## Cuando usarla
- Vas a marcar una tarea como completa — review final antes de entregar
- Usuario pide "revisa este codigo" o "que opinas"
- Antes de un commit grande (>100 lineas o >3 archivos)
- Despues de un refactor, antes de mergear a main

## Cuando NO usarla
- Cambio trivial (typo, 1-3 lineas)
- Codigo experimental que se va a tirar
- Aun no terminaste de implementar — primero termina, despues revisa

## Checklist

### Correctitud
- [ ] ¿Hace lo que el pedido pide? (releer el pedido original)
- [ ] Edge cases manejados: empty, null, negative, huge, unicode, concurrent
- [ ] ¿Que pasa si la DB no responde / la API externa timea / el archivo no existe?
- [ ] Off-by-one: rangos `[a, b)` vs `[a, b]`, indices 0 vs 1
- [ ] Locale: comparaciones de strings, formato de numeros/fechas
- [ ] Tests cubren los paths felices Y al menos un edge case

### Seguridad
- [ ] Input del usuario NO va directo a SQL/shell/HTML sin sanitizar
- [ ] Secrets NO hardcodeados (API keys, passwords, tokens)
- [ ] Auth chequeada antes de operaciones sensibles
- [ ] Logs NO contienen secrets ni PII
- [ ] Limites en uploads, paginacion, recursion

### Claridad
- [ ] Nombres dicen QUE es la cosa (no `data`, `tmp`, `mgr`)
- [ ] Funciones cortas — si tiene >40 lineas o >3 niveles de indent, pregunta si vale extraer
- [ ] Comentarios explican POR QUE, no QUE (el codigo dice el que)
- [ ] No hay codigo muerto / imports muertos / variables sin uso
- [ ] No hay TODOs sin owner ni fecha

### Estilo / convenciones del proyecto
- [ ] Sigue las convenciones del repo (naming, layout, patrones existentes)
- [ ] No introduce dep nueva si una existente resolvia
- [ ] Tipos: si el repo usa typing, lo nuevo tambien (Python `type hints`, TS `strict`, Rust ya forzado)

### Errores
- [ ] No hay `try: ... except: pass` (silenciar errores sin razon)
- [ ] Errores propagan con contexto (no `raise Exception("error")` generico)
- [ ] Resources se cierran (DB connections, files, sockets) — `with`/`defer`/RAII
- [ ] Race conditions en codigo concurrente

### Performance (solo si aplica)
- [ ] N+1 queries: `for x in xs: db.query(x.id)` → batch o join
- [ ] Loops anidados sobre datos grandes
- [ ] String concat en loops (usar join/buffer)
- [ ] Resources costosos (clients, pools) creados por request en vez de reusados

### Tests
- [ ] Existen y pasan en verde
- [ ] Cubren happy path + al menos un edge case
- [ ] No son tautologicos (mockean todo y verifican que se llamo el mock)
- [ ] No dependen de orden / DB sucia / network real

### Git hygiene (si vas a commitear)
- [ ] Diff contiene solo lo necesario (no debug prints, no archivos accidentales)
- [ ] Mensaje de commit dice POR QUE, no solo QUE
- [ ] Un commit = un concepto coherente

## Como dar feedback
- **Bug**: "Si X pasa, esto rompe porque Y. Fix sugerido: Z."
- **Mejora opcional**: "Esto funciona. Considera Z porque W — pero no es bloqueante."
- **Preferencia**: separar lo objetivo (bugs) de lo subjetivo (estilo).

## Ejemplos

**Input:** "termine la feature de login, revisala antes de marcar hecho"
**Accion:**
1. Releer el pedido original
2. `git diff main` para ver el cambio entero
3. Correr el checklist arriba
4. Listar findings en 3 grupos: bloqueantes (bugs/security), recomendados (claridad/perf), opcionales (estilo)
5. Para cada bloqueante: arreglar antes de marcar hecho

**Input:** "que opinas de este handler" (pega codigo)
**Accion:**
1. Leerlo entero antes de comentar
2. Marcar lo bueno (no es solo criticar)
3. Listar findings en orden de importancia
4. Sugerir cambios concretos, no abstractos ("usa X" mejor que "esto deberia ser mas claro")
