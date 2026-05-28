---
name: search-docs
description: Buscar y leer documentacion oficial de lenguajes/libs/frameworks via shell — Python, MDN, FastAPI, SvelteKit, Rust, npm/crates/pypi. Cargala cuando necesitas el comportamiento exacto de una API, signature de funcion, opciones de un comando, o cambios de version. Mas precisa que `web-search` cuando ya sabes en que docs buscar.
---

# Skill: search-docs

## Cuando usarla
- "Como funciona X funcion / metodo / config"
- "Cuales son los parametros de Y"
- "Que cambio en la version Z"
- Tu memoria sobre una API es vieja o dudosa — verificar antes de codear
- El usuario reporta error de una lib → buscar en sus docs

## Cuando NO usarla
- Busqueda generica / opiniones / comparativas → `web-search`
- La info ya esta en el repo (vendor/, node_modules/, .venv/) — leela del filesystem
- Es comportamiento de codigo del usuario, no de la lib

## Sitios indexados y como buscar

### Python stdlib
- Base: `https://docs.python.org/3/`
- Search: `https://docs.python.org/3/search.html?q=QUERY`
- Modulo directo: `https://docs.python.org/3/library/MODULO.html`

### MDN (JS / Web APIs / HTML / CSS)
- Search: `https://developer.mozilla.org/en-US/search?q=QUERY`
- Directo: `https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API`

### FastAPI
- Base: `https://fastapi.tiangolo.com/`
- Search funciona via DDG con `site:fastapi.tiangolo.com QUERY`

### SvelteKit / Svelte
- SvelteKit docs: `https://svelte.dev/docs/kit/`
- Svelte docs: `https://svelte.dev/docs/svelte/`
- Search: `site:svelte.dev QUERY` via DDG

### Rust
- Lang reference: `https://doc.rust-lang.org/reference/`
- Std: `https://doc.rust-lang.org/std/`
- Std search: `https://doc.rust-lang.org/std/?search=QUERY`
- Crates (ecosistema): `https://docs.rs/CRATE/latest/CRATE/`
- Crates.io metadata: `https://crates.io/api/v1/crates/CRATE`

### Actix Web especifico
- `https://actix.rs/docs/` (guia)
- `https://docs.rs/actix-web/latest/actix_web/` (API)

### Node / npm
- npm package: `https://registry.npmjs.org/PAQUETE` (JSON oficial — versiones, deps)
- Node docs: `https://nodejs.org/api/`

### PyPI
- Paquete: `https://pypi.org/pypi/PAQUETE/json` (JSON, devuelve version, deps, urls)

## Procedimiento

### 1. Identificar el sitio correcto
Mapear el pedido al sitio. Si el usuario pregunta por `async def`, es Python stdlib → docs.python.org. Si pregunta por `web::Json`, es Actix → docs.rs/actix-web.

### 2. Fetchear directo cuando hay URL determinista
```bash
python -c "
import urllib.request, re, html
url = 'https://docs.python.org/3/library/asyncio-task.html'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
# Quedarse con el body principal
text = re.sub(r'<script.*?</script>', '', raw, flags=re.S|re.I)
text = re.sub(r'<style.*?</style>', '', text, flags=re.S|re.I)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(re.sub(r'\s+', ' ', text)).strip()
# Buscar la seccion relevante
i = text.lower().find('asyncio.gather')
print(text[max(0,i-200):i+2000])
"
```

### 3. Si no sabes la URL exacta: site search via DDG
```bash
python -c "
import urllib.request, urllib.parse, re, html
q = urllib.parse.quote_plus('site:svelte.dev/docs \$state runes')
req = urllib.request.Request(
    f'https://lite.duckduckgo.com/lite/?q={q}',
    headers={'User-Agent': 'Mozilla/5.0'}
)
data = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', 'replace')
links = re.findall(r'<a[^>]+class=\"result-link\"[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>', data, re.S)
strip = lambda s: html.unescape(re.sub(r'<[^>]+>', '', s)).strip()
for url, title in links[:5]:
    print(strip(title), '->', url)
"
```

Despues fetcheas la URL mas prometedora con el snippet de (2).

### 4. APIs JSON (mas faciles que HTML)
PyPI y crates.io devuelven JSON estructurado. Ejemplo PyPI:
```bash
python -c "
import urllib.request, json
data = json.loads(urllib.request.urlopen('https://pypi.org/pypi/fastapi/json', timeout=15).read())
info = data['info']
print('version:', info['version'])
print('summary:', info['summary'])
print('home:', info['home_page'] or info.get('project_urls', {}))
print('requires:', info['requires_dist'][:10] if info['requires_dist'] else [])
"
```

### 5. Devolver al usuario
- Citá la URL exacta (no "segun la doc...")
- Quote el texto relevante (no parafrasees mal)
- Si la doc dice "deprecated since X", *resaltalo*
- Diferenciar version: si el repo usa lib v3 y la doc es de v4, advertir

## Reglas
- **Verifica version**: docs cambian entre majors. Antes de citar, asegurate de leer la version que el repo usa (revisa `pyproject.toml`/`package.json`/`Cargo.toml`).
- **No inventes URLs**: si no estas seguro de la url, primero buscala via site search.
- **Una pagina ≠ una respuesta**: a veces necesitas leer 2-3 paginas para tener el panorama (guia + reference + changelog).

## Trampas
- Docs viejas en cache de Google. Preferi search directo del sitio antes que DDG cuando hay search interno.
- Algunas docs (Rust std) son JS-rendered en su buscador → fetchear la pagina del item directo (`/std/struct.Vec.html`) funciona mejor.
- Snippets de docs.rs son a veces incompletos. Si el comportamiento no esta claro, leer el source linkeado.

## Ejemplos

**Input:** "como uso `$derived.by` en Svelte 5"
**Accion:**
1. URL directa: `https://svelte.dev/docs/svelte/$derived`
2. Fetchear y buscar substring `derived.by` en el texto
3. Citar el ejemplo oficial y la signature
4. Si hay caveats (cuando NO usarla), incluirlos

**Input:** "que version de pydantic requiere la ultima fastapi"
**Accion:**
1. `pypi.org/pypi/fastapi/json` → ver `requires_dist`
2. Buscar la linea `pydantic ...` en `requires_dist`
3. Responder con el rango exacto + link a PyPI

**Input:** "como hago un middleware custom en actix-web 4"
**Accion:**
1. Verificar version en `Cargo.toml` (confirmar v4.x)
2. Fetch `https://actix.rs/docs/middleware/` y `https://docs.rs/actix-web/latest/actix_web/dev/trait.Transform.html`
3. Sintetizar pasos + snippet idiomatico citando ambas paginas
