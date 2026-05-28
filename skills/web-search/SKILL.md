---
name: web-search
description: Buscar informacion en internet via shell — usa DuckDuckGo Lite (sin API key, HTML simple parseable). Cargala cuando el usuario pide "buscame X", "que hay sobre Y", "encontra info de Z", o cuando necesitas datos que no estan en el repo ni en tu conocimiento.
---

# Skill: web-search

## Cuando usarla
- "Buscame info sobre X"
- "Que dice internet de Y"
- "Como hace la gente Z" (busqueda generica, no docs especificas)
- Necesitas datos actualizados (precios, fechas, eventos, releases)
- Estas inseguro y queres validar antes de afirmar

## Cuando NO usarla
- Buscas documentacion oficial de una lib/lang → usa `search-docs` en su lugar
- La respuesta esta en archivos del workspace → primero `list_dir`/`grep`
- Es trivia que sabes con alta confianza → contesta directo, no busques porque si

## Como funciona
No hay tool de web nativa. Usamos `python` (siempre disponible) + DuckDuckGo Lite (HTML simple, sin JS, sin API key). Funciona para top results — titulos, snippets, urls.

## Procedimiento

### 1. Busqueda basica
```bash
python -c "
import urllib.request, urllib.parse, html, re, sys
q = urllib.parse.quote_plus('TU QUERY ACA')
req = urllib.request.Request(
    f'https://lite.duckduckgo.com/lite/?q={q}',
    headers={'User-Agent': 'Mozilla/5.0'}
)
data = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'replace')
# Resultados estan en <a class='result-link' href='URL'>TITULO</a> + snippet siguiente
links = re.findall(r'<a[^>]+class=\"result-link\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>', data, re.S)
snippets = re.findall(r'<td[^>]*class=\"result-snippet\"[^>]*>(.*?)</td>', data, re.S)
strip = lambda s: html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
for i, ((url, title), snip) in enumerate(zip(links[:10], snippets[:10]), 1):
    print(f'{i}. {strip(title)}')
    print(f'   {url}')
    print(f'   {strip(snip)[:200]}')
    print()
"
```

Reemplaza `TU QUERY ACA` por la query real. Te devuelve top 10 con titulo + url + snippet.

### 2. Fetch del contenido de un resultado
Cuando uno de los resultados parece relevante, leelo:
```bash
python -c "
import urllib.request, re, html
req = urllib.request.Request('URL_AQUI', headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
# Limpiar HTML basico (no es perfecto pero suficiente para texto)
text = re.sub(r'<script.*?</script>', '', raw, flags=re.S|re.I)
text = re.sub(r'<style.*?</style>', '', text, flags=re.S|re.I)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(re.sub(r'\s+', ' ', text)).strip()
print(text[:5000])
"
```

Si el resultado es JSON (API): no parseas HTML, leelo directo con `json.loads`.

### 3. Filtros utiles en la query
- `"frase exacta"` — match literal
- `-palabra` — excluir
- `site:dominio.com` — solo de ese dominio
- `2025` o `after:2024-01-01` — recencia (DDG lo respeta a medias)

### 4. Si DDG falla o esta rate-limited
Fallback: probar la API de DuckDuckGo Instant Answer (solo para queries que tienen "answer box"):
```bash
python -c "
import urllib.request, urllib.parse, json
q = urllib.parse.quote_plus('python release date 3.13')
url = f'https://api.duckduckgo.com/?q={q}&format=json&no_html=1'
data = json.loads(urllib.request.urlopen(url, timeout=10).read())
print(data.get('AbstractText') or data.get('Answer') or '[sin instant answer]')
print('Source:', data.get('AbstractURL'))
"
```

## Reglas de uso responsable
- **Una busqueda por necesidad**, no spam. Cada query cuesta ~1s y consume el rate limit de DDG.
- **No expongas datos sensibles en queries** (PII, secrets, etc).
- **Verifica antes de afirmar**: si el snippet dice algo, fetcheá la pagina para confirmar contexto. Snippets a menudo se sacan de contexto.
- **Citá la fuente**: cuando uses info encontrada, decile al usuario de donde salio (URL). Asi puede verificar.
- **Recency**: DDG no garantiza freshness. Para datos muy recientes (release de hoy, breaking news), advertir al usuario.

## Trampas
- HTML de DDG puede cambiar — si el regex deja de matchear, mostrar el raw y adaptar
- Algunos sitios bloquean User-Agent generico → algunos snippets son inutiles
- Rate limit: si te dan 429, esperá. NO retries en bucle.
- Contenido JS-rendered (SPAs) no se ve con curl — solo el shell HTML

## Ejemplos

**Input:** "buscame la ultima version de FastAPI"
**Accion:**
1. Query: `FastAPI latest version 2026`
2. Top results probablemente apunten a github releases o pypi
3. Fetchear github.com/tiangolo/fastapi/releases/latest o pypi.org/project/fastapi/
4. Responder con version + fecha + link

**Input:** "que dicen de Coolify vs Dokku en 2026"
**Accion:**
1. Query: `Coolify vs Dokku 2025 review`
2. Top 5 resultados — leer 2 que parezcan mas comparativos
3. Sintetizar pros/contras con citas a los posts
4. NO inventes opiniones que no aparecen en los textos
