---
name: professional-ui-design
description: Diseno UI/UX profesional para apps web con SvelteKit + Tailwind 4. Cargala cuando el usuario pida construir una interfaz, pagina, dashboard, landing, o cualquier cosa visual. Antes de codear, produce un DESIGN.md con el sistema de diseno. Anti-AI-slop: nada de generico, nada de boilerplate.
---

# Skill: Diseno UI/UX Profesional

## Cuando usarla
- El usuario pide "hace una UI", "disena una pagina", "arma un dashboard", "landing page", "interfaz de usuario"
- El usuario pide que se vea "profesional", "moderno", "lindo", "no generico"
- Despues del planner, cuando toca implementar el frontend
- Cuando el subagent sveltekit-expert va a generar codigo visual

## Cuando NO usarla
- APIs, backends, scripts de consola, bots
- Tasks puramente logicas sin UI

## Procedimiento

### Fase 0: Brief Inference (antes de codear)

Antes de escribir HTML/CSS, declara en una linea el "Design Read":

> **[tipo de pagina]** para **[audiencia]** — vibe **[palabras clave]** — sistema: **[familia de diseno]**

Ej: "Dashboard SaaS para startups fintech — vibe clean/dark-tech — sistema: shadcn-ui"

Si el brief es ambiguo, hace 1 pregunta clarificadora maximo. Seis seniales a evaluar:
1. Tipo de pagina (landing, dashboard, blog, app, portfolio, e-commerce)
2. Palabras vibe (clean, dark, playful, editorial, brutalist, premium, minimal)
3. URLs de referencia si hay
4. Audiencia objetivo
5. Branding existente (colores, logo)
6. Restricciones silenciosas (accesibilidad, rendimiento, movil)

### Fase 1: DESIGN.md — Sistema de Diseno (OBLIGATORIO antes de codear)

Crea un archivo `DESIGN.md` en la raiz del proyecto con estas 9 secciones. TODO antes de tocar un `.svelte`:

1. **Tema visual y atmosfera** — 2-3 lineas describiendo la sensacion
2. **Paleta de colores** — max 1 color acento, saturacion < 80%. Variables CSS `--color-*` con valores oklch. Incluir RGB helper.
3. **Tipografia** — font families (max 2), jerarquia de tamanios, Google Fonts URL. **NUNCA** Inter o Roboto como default. Alternativas: Geist, Outfit, Cabinet Grotesk, Satoshi, Plus Jakarta Sans.
4. **Componentes base** — botones (todos los estados: hover, active, disabled, focus), cards, nav, links, tags, inputs
5. **Layout** — grid system, breakpoints, sidebar o no, max-width
6. **Elevacion y sombras** — cuando usar sombra, profundidad
7. **Animacion e interaccion** — transiciones, hover effects, page transitions (Svelte `transition:fade` o `fly`)
8. **Do's y Don'ts** — minimo 8 reglas especificas del proyecto
9. **Responsive** — comportamiento en mobile, tablet, desktop

### Fase 2: Anti-AI-Slop Rules (NO NEGOCIABLES)

Estas reglas se aplican SIEMPRE al generar codigo:

#### Color
- NADA de gradients purple-pink-blue por default
- NADA de glows neon o purpura en botones
- Maximo 1 color acento. Usalo consistentemente en toda la pagina.
- Fondo blanco puro solo si es editorial. Preferi `#f8f9fa`, `#f5f5f0`, o similar.
- **BAN** paleta "premium-consumer" generica: fondos #f5f1ea, #f7f5f1, acentos #b08947, #b6553a

#### Tipografia
- **NUNCA** Inter como default sin justificacion. Alternativas: Geist, Outfit, Satoshi, Cabinet Grotesk
- Jerarquia clara: h1 una sola vez por pagina, h2 para secciones, h3 sub-secciones
- Body text 16px en desktop, 15px en mobile (minimo)
- Line-height: 1.5-1.7 para body, 1.1-1.3 para headings
- **BAN** Fraunces e Instrument_Serif como default

#### Layout
- **BAN** tarjetas de 3 columnas iguales con icono+texto (el patron mas generico de IA)
- **BAN** layout centerizado simetrico en todo — varia: split, left-aligned, scroll-pinned
- Hero debe entrar en el viewport: headline max 2 lineas, subtext max 20 palabras, CTAs visibles sin scroll
- **BAN** "zigzag" de image+texto mas de 2 veces seguidas
- 4+ secciones en landing = al menos 3 familias de layout diferentes

#### Contenido
- **NUNCA** em-dash (`—`) en texto visible. Usa guion comun o nada.
- **NUNCA** nombres genericos ("John Doe", "Sarah Chan")
- **NUNCA** "Elevate", "Seamless", "Unleash", "Revolutionary", "Next-Gen"
- **NUNCA** logos de "marcas ficticias" — no inventes testimonios ni estadisticas
- Texto real, no lorem ipsum (salvo structural placeholder acordado)
- Headlines cortos: <= 8 palabras. Parrafos <= 25 palabras.

#### Imagenes
- **BAN** divs de color como placeholder de imagen
- **BAN** screenshots falsos hechos con divs estilados
- Usa Unsplash con seeds descriptivos o placeholder slots honestos

### Fase 3: Implementacion SvelteKit + Tailwind 4

#### Estructura base del proyecto SvelteKit (verificar siempre):
```
src/
├── routes/
│   ├── +layout.svelte     ← IMPORTANTE: import '../app.css' para Tailwind 4
│   ├── +layout.ts         ← opcional, layout load
│   ├── +page.svelte       ← landing/default
│   ├── +page.ts           ← opcional, page load
│   └── +error.svelte      ← SIEMPRE, nunca 404 generico de SvelteKit
├── lib/
│   ├── components/        ← componentes reusables
│   ├── server/
│   │   └── db.ts          ← lazy connection a Mongo
│   └── types.ts           ← tipos compartidos
├── app.html
├── app.css                ← Tailwind 4 import + variables CSS globales
├── app.d.ts
```

#### Checklist Svelte 5 (siempre verificar):
- [ ] `+layout.svelte` raiz: `let { children } = $props();` + `{@render children()}`
- [ ] `import '../app.css'` en layout raiz para Tailwind 4
- [ ] `+page.svelte` con load: `let { data } = $props();`
- [ ] `$state()` en vez de `let` reactivo legacy
- [ ] `$derived()` en vez de `$:` para valores computados
- [ ] `+error.svelte` para manejo de errores
- [ ] `+page.ts` server load para datos (no `onMount` para fetch de API)

#### Componentes (Svelte 5 con runes):
```svelte
<script lang="ts">
  let { title, href, variant = 'primary' }: { title: string; href?: string; variant?: 'primary' | 'secondary' | 'ghost' } = $props();
</script>
```

#### Tailwind 4:
- Usa `@theme` en `app.css` para definir design tokens
```css
@import "tailwindcss";
@theme {
  --color-primary: oklch(0.55 0.2 260);
  --color-surface: oklch(0.97 0.01 260);
  --font-display: "Geist", sans-serif;
  --font-body: "Outfit", sans-serif;
}
```

### Fase 4: Estados de UI (OBLIGATORIO para cada componente)

Cada componente que muestra datos debe contemplar:
1. **Loading state** — skeleton o spinner mientras carga
2. **Empty state** — "No hay items" con accion para crear el primero
3. **Error state** — mensaje claro + opcion de reintentar
4. **Success state** — datos visibles
5. **Edge cases** — texto muy largo, valores nulos, paginas 404

### Fase 5: Verificacion Pre-Flight (antes de entregar)

Checklist obligatorio:
- [ ] Sin errores de consola (dev tools)
- [ ] Navegacion por teclado funciona (Tab, Enter, Escape)
- [ ] 4 breakpoints: 320px, 768px, 1024px, 1440px
- [ ] Contraste WCAG AA 4.5:1 en texto normal
- [ ] Estados hover/focus/active en todos los interactivos
- [ ] Empty states implementados
- [ ] Sin em-dashes ni nombres genericos
- [ ] Sin gradients purple-pink por defecto
- [ ] Layout varia entre secciones (no todo igual)
- [ ] Hero entra en viewport sin scroll
- [ ] Sin divs de color como placeholder de imagen

## Formato de salida
- DESIGN.md completo primero (fase 1-2)
- Archivos implementados con [MANIFEST] al final
- Verificacion pre-flight completada
- URL de preview si deployaste

## Tools disponibles
read_file, write_file, list_dir, shell, load_skill (para cargar coolify-deploy si deployas), spawn_subagent (al sveltekit-expert para implementar siguiendo este DESIGN.md)
