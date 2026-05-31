---
name: ui-ux-pro-max
description: "Diseno UI/UX profesional con 10 categorias priorizadas. 50+ estilos, 161 paletas, 57 pares tipograficos, 161 tipos de producto. Para SvelteKit + Tailwind 4."
---

# UI/UX Pro Max — Diseno Inteligente

Skill de diseno profesional adaptada de UI/UX Pro Max (NextLevelBuilder). Cubre 10 categorias priorizadas de diseno UI/UX para web y mobile, adaptada al stack SvelteKit + Tailwind 4 + MongoDB.

## Cuando usarla

### USALA SIEMPRE
- Disenar paginas nuevas (landing, dashboard, admin, SaaS, mobile)
- Crear o refactorizar componentes UI (botones, modales, forms, tablas, charts)
- Elegir paletas de color, tipografia, espaciado, layouts
- Revisar UI por accesibilidad o consistencia visual
- Implementar navegacion, animaciones, responsive
- Antes de buildear cualquier frontend
- Cuando la UI "no se ve profesional" pero no sabes por que
- Pre-lanzamiento: optimizacion de calidad visual

### NO USARLA
- Backend puro, APIs, DB, scripts, CI/CD, infraestructura
- Tareas no visuales o de automatizacion

**Regla**: si la tarea cambia como algo SE VE, SE SIENTE, SE MUEVE O SE INTERACTUA — usa esta skill.

## Categorias por Prioridad

Siempre empeza por prioridad mas alta (1 = CRITICAL) y segui hacia abajo. No te saltes categorias.

| Prio | Categoria | Impacto | Dominio |
|------|-----------|---------|---------|
| 1 | Accesibilidad | CRITICAL | ux |
| 2 | Touch & Interaccion | CRITICAL | ux |
| 3 | Performance | HIGH | ux |
| 4 | Seleccion de Estilo | HIGH | style, product |
| 5 | Layout & Responsive | HIGH | ux |
| 6 | Tipografia & Color | MEDIUM | typography, color |
| 7 | Animacion | MEDIUM | ux |
| 8 | Formularios & Feedback | MEDIUM | ux |
| 9 | Navegacion | HIGH | ux |
| 10 | Charts & Datos | LOW | chart |

---

## 1. Accesibilidad (CRITICAL)

Reglas obligatorias en TODA UI:

- **Contraste**: minimo 4.5:1 texto normal, 3:1 texto grande (WCAG AA)
- **Focus states**: `outline` visible en todo elemento interactivo. NUNCA `outline: none` sin alternativa
- **Alt text**: toda imagen significativa tiene `alt` descriptivo
- **ARIA labels**: botones solo-icono tienen `aria-label`
- **Keyboard nav**: orden Tab coincide con orden visual. Todo interactivo accesible por teclado
- **Form labels**: `<label for="id">` asociado a cada input
- **Skip link**: link "Saltar al contenido" al inicio de la pagina
- **Heading hierarchy**: `h1` → `h2` → `h3` secuencial, sin saltos
- **Color not only**: no uses solo color para transmitir informacion — agrega icono/texto
- **Reduced motion**: respeta `prefers-reduced-motion` — desactiva animaciones cuando esta activo
- **Screen readers**: `role="alert"` en errores, `aria-live="polite"` en toasts, `aria-modal` en dialogos
- **Escape routes**: modales y flujos multi-paso tienen boton cancelar/cerrar (Escape)
- **VoiceOver/SR**: `aria-label` descriptivo en elementos interactivos, orden de lectura logico

### SvelteKit:
```svelte
<!-- skip link -->
<a href="#main-content" class="sr-only focus:not-sr-only focus:absolute">
  Saltar al contenido
</a>
<main id="main-content">
  <!-- contenido -->
</main>

<!-- modal accesible -->
<svelte:window onkeydown={(e) => e.key === 'Escape' && onClose()} />
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div role="dialog" aria-modal="true" aria-labelledby="modal-title"
     onkeydown={(e) => e.key === 'Escape' && onClose()}>
  <h2 id="modal-title">{title}</h2>
  <button onclick={onConfirm}>Confirmar</button>
  <button onclick={onClose} autofocus>Cancelar</button>
</div>
```

## 2. Touch & Interaccion (CRITICAL)

- **Touch targets**: minimo 44x44px (Apple) / 48x48dp (Material). Botones, links, iconos
- **Espaciado**: minimo 8px entre targets tactiles
- **Hover vs tap**: no uses hover como unica interaccion — en mobile no existe
- **Loading buttons**: deshabilitar el boton durante async, mostrar spinner
- **Error feedback**: errores claros CERCA del campo, no solo arriba
- **Cursor pointer**: `cursor-pointer` en todo clickable
- **Tap delay**: `touch-action: manipulation` para eliminar delay de 300ms
- **Press feedback**: feedback visual en cada presion (scale 0.97, color change, Tailwind `active:`)
- **Swipe clarity**: acciones swipe deben tener indicacion visual (chevron, hint)
- **Safe areas**: mantener targets tactiles lejos de notch, Dynamic Island, gesture bar

### Tailwind 4:
```css
/* touch optimization */
button, a, [role="button"] {
  touch-action: manipulation;
  cursor: pointer;
}

/* press feedback */
.btn-press {
  transition: transform 100ms;
}
.btn-press:active {
  transform: scale(0.97);
}
```

## 3. Performance (HIGH)

- **Image optimization**: WebP/AVIF, `loading="lazy"`, `srcset`/`sizes`
- **CLS prevention**: declarar `width`/`height` en imagenes, `aspect-ratio` en contenedores
- **Font loading**: `font-display: swap` en `@font-face`
- **Lazy loading**: lazy load imagenes below-fold, dynamic import de componentes pesados
- **Bundle splitting**: SvelteKit ya hace code-splitting por ruta. No romperlo
- **Third-party**: `async`/`defer` en scripts de terceros
- **Content jumping**: reservar espacio para contenido async (skeleton)
- **Skeleton screens**: shimmer/skeleton para operaciones >300ms
- **Debounce**: en eventos de alta frecuencia (scroll, resize, input)

### SvelteKit:
```typescript
// lazy load component
import($page => import(`./components/${page}.svelte`))
```

## 4. Seleccion de Estilo (HIGH)

Anti-AI-slop rules + UI/UX Pro Max:

- **Estilo coherente**: elegir un estilo (glassmorphism, minimal, bento, flat) y mantenerlo en TODO el sistema. No mezclar

- **Color palette**: maximo 1 color de acento. Usar `oklch()` para paletas perceptualmente uniformes. Saturacion <80% para acentos, <50% para fondos

- **BANNED palettes**: ninguna de estas:
  - `#f5f1ea` con `#b08947` (premium-consumer slop)
  - `#0f172a` con `#3b82f6` y `#8b5cf6` (startup slop)
  - `#ffffff` con `#f59e0b` y `#6366f1` (SaaS default)
  - Purpuras en gradients (nunca)

- **SVG icons**: usar Heroicons o Lucide. NUNCA emojis como iconos

- **Typography**: nunca Inter, nunca Roboto. Preferir: Geist, Outfit, Satoshi, DM Sans, Cabinet Grotesk, General Sans

- **Font pairing**: heading bold (600-700), body regular (400). Usar `font-display: swap`

- **Effects**: sombras, blur, border-radius alineados con el estilo elegido. NUNCA valores aleatorios

- **Dark mode**: disenar light/dark juntos. Modo oscuro usa variantes desaturadas, no invertir colores

- **Primary action**: cada pantalla tiene UNA sola CTA primaria. Acciones secundarias visualmente subordinadas

### SvelteKit + Tailwind 4:
```css
/* tokens en app.css */
:root {
  --color-primary: oklch(0.55 0.15 250);
  --color-surface: oklch(0.98 0.01 250);
  --color-text: oklch(0.15 0.02 250);
  --font-heading: 'Geist', sans-serif;
  --font-body: 'DM Sans', sans-serif;
}
```

## 5. Layout & Responsive (HIGH)

- **Mobile-first**: disenar mobile primero, escalar a tablet y desktop
- **Viewport**: `width=device-width, initial-scale=1` — NUNCA deshabilitar zoom
- **Breakpoints**: Tailwind por defecto: `sm: 40rem`, `md: 48rem`, `lg: 64rem`, `xl: 80rem`, `2xl: 96rem`
- **Body font**: minimo 16px en mobile (evita auto-zoom de iOS)
- **Line length**: 35-60 chars mobile, 60-75 desktop
- **Horizontal scroll**: NUNCA. Todo contenido debe caber en el viewport
- **Spacing scale**: 4/8/12/16/24/32/48/64 — consistente en todo el sistema
- **Touch density**: espaciado comodo entre componentes, ni apretado ni suelto
- **Container**: `max-w-6xl` o `max-w-7xl` en desktop
- **Z-index scale**: valores definidos: 0/10/20/40/100/1000
- **Visual hierarchy**: jerarquia via tamanio, espaciado, contraste — no solo color
- **BANNED**: tarjetas de 3 columnas iguales, zigzag infinito de imagen-texto

### Tailwind 4 (app.css):
```css
@import "tailwindcss";

@theme {
  --breakpoint-xs: 20rem;
  --container-6xl: 72rem;
  --container-7xl: 80rem;
}
```

## 6. Tipografia & Color (MEDIUM)

### Tipografia
- **Line height**: 1.5-1.75 body, 1.1-1.3 headings
- **Line length**: max 75 caracteres por linea
- **Font scale**: 12/14/16/18/24/32/48/64
- **Font weight**: headings 600-700, body 400, labels 500
- **BANNED**: Inter, Roboto, em-dash (`—`), `__` en nombres de variables

### Color
- **Semantic tokens**: definir `primary`, `secondary`, `error`, `surface`, `on-surface` NUNCA hex raw en componentes
- **Dark mode**: variantes desaturadas, testear contraste separadamente
- **Accesible pairs**: 4.5:1 minimo. Usar `oklch()` para consistencia perceptual
- **Functional color**: si usas color para estado (error=rojo, success=verde), incluir icono/texto
- **BANNED**: gradients purple, `#f5f1ea`+`#b08947`, `#0f172a`+`#3b82f6`+`#8b5cf6`

### Tailwind 4 tokens:
```css
@theme {
  --color-primary: oklch(0.55 0.15 250);
  --color-primary-light: oklch(0.65 0.12 250);
  --color-primary-dark: oklch(0.45 0.15 250);
  --color-surface: oklch(0.98 0.01 250);
  --color-surface-dark: oklch(0.12 0.02 250);
  --color-text: oklch(0.15 0.02 250);
  --color-text-dark: oklch(0.85 0.02 250);
  --color-error: oklch(0.55 0.2 25);
  --color-success: oklch(0.55 0.15 145);
  --font-heading: 'Geist', sans-serif;
  --font-body: 'DM Sans', sans-serif;
}
```

## 7. Animacion (MEDIUM)

- **Duration**: 150-300ms micro-interacciones, <=400ms transiciones complejas
- **Performance**: solo `transform` y `opacity` — NUNCA animar `width`/`height`/`top`/`left`
- **Loading**: skeleton/spinner si la operacion toma >300ms
- **Motion meaning**: cada animacion expresa causa-efecto. NUNCA decorativa
- **Easing**: `ease-out` para entrada, `ease-in` para salida. NUNCA linear
- **Exit faster**: animaciones de salida 60-70% de la duracion de entrada
- **Reduced motion**: `prefers-reduced-motion` — desactivar animaciones
- **Stagger**: listas/grids entran con 30-50ms de delay por item
- **Continuity**: transiciones entre paginas con shared elements, slide direccional

### SvelteKit:
```svelte
<!-- page transition -->
<div in:fly={{ y: 20, duration: 300 }} out:fade={{ duration: 200 }}>
  <slot />
</div>

<!-- conditional animation -->
<script>
  let motionOk = $state(true);
  onMount(() => {
    motionOk = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
</script>
```

## 8. Formularios & Feedback (MEDIUM)

- **Labels visibles**: NUNCA placeholder como unico label
- **Error near field**: mensaje de error debajo del campo, no solo arriba
- **Submit feedback**: loading → success/error en el boton de submit
- **Required indicators**: asterisco en campos requeridos
- **Empty states**: mensaje util + accion (boton crear) cuando no hay contenido
- **Toast dismiss**: auto-dismiss a los 3-5s
- **Confirmation**: confirmar antes de acciones destructivas (modal rojo)
- **Double submit prevention**: deshabilitar boton despues del primer click
- **Validation on blur**: validar al salir del campo, no en cada tecla
- **Keyboard types**: `type="email"`, `type="tel"`, etc. para teclado correcto en mobile
- **Password toggle**: boton mostrar/ocultar en campos password
- **Auto-focus**: al primer campo con error despues de submit
- **Error recovery**: mensajes que digan QUE paso y COMO arreglarlo

### SvelteKit + Tailwind 4:
```svelte
<form method="POST" use:enhance>
  <label for="email" class="block text-sm font-medium">Email *</label>
  <input
    id="email" name="email" type="email" required
    class="block w-full rounded-lg border px-3 py-2
           aria-[invalid=true]:border-red-500"
    aria-invalid={!!errors?.email}
    aria-describedby={errors?.email ? 'email-error' : undefined}
    bind:value={email}
  />
  {#if errors?.email}
    <p id="email-error" role="alert" class="mt-1 text-sm text-red-500">
      {errors.email}
    </p>
  {/if}
  <button type="submit" disabled={submitting}
          class="mt-4 rounded-lg bg-primary px-4 py-2 text-white
                 disabled:opacity-50">
    {submitting ? 'Guardando...' : 'Guardar'}
  </button>
</form>
```

## 9. Navegacion (HIGH)

- **Bottom nav**: max 5 items, icon+label. Solo para pantallas top-level
- **Back button**: comportamiento de retroceso predecible, preservar scroll/estado
- **Deep linking**: toda pantalla key alcanzable por URL/deep link
- **Active state**: ubicacion actual visualmente resaltada en nav
- **Breadcrumbs**: para jerarquias de 3+ niveles
- **404 page**: personalizada con link a home
- **Modal escape**: toda modal tiene boton cerrar + Escape
- **Tab bar (iOS)**: bottom Tab Bar para nav principal
- **Sidebar (desktop)**: sidebar para navegacion en pantallas >=1024px
- **State preservation**: volver atras restaura scroll y estado de filtros
- **Search accessible**: busqueda facil de alcanzar (top bar o tab)
- **Consistency**: navegacion igual en TODAS las paginas
- **BANNED**: mezclar Tab + Sidebar + Bottom Nav al mismo nivel

### SvelteKit:
```typescript
// hooks.server.ts — redirect sin auth
export function handle({ event, resolve }) {
  const session = event.cookies.get('session');
  if (!session && event.url.pathname.startsWith('/dashboard')) {
    throw redirect(303, '/login');
  }
  return resolve(event);
}
```

## 10. Charts & Datos (LOW)

- **Chart type**: linea (trends), barra (comparacion), pie/donut (proporcion, max 5 categorias)
- **Color accessible**: paletas accesibles, evitar solo rojo/verde
- **Legend**: siempre visible, no detached below scroll fold
- **Tooltip**: hover/click muestra valores exactos
- **Axis labels**: unidades claras, escala legible
- **Empty state**: "No hay datos" con guidance, nunca chart vacio
- **Loading**: skeleton mientras carga, nunca frame vacio
- **Responsive**: chart se reflow o simplifica en mobile
- **Sortable table**: datos tabulares soportan sorting con `aria-sort`
- **Number format**: locale-aware para numeros, fechas, monedas

## Anti-AI-Slop Checklist (REFUERZO)

Antes de escribir cualquier codigo UI, verificar:

- [ ] NO usar Inter o Roboto como fuente principal
- [ ] NO usar em-dash (`—`) en textos
- [ ] NO usar `__` (doble underscore) en nombres de clases/variables
- [ ] NO mas de 1 color de acento
- [ ] NO gradients purple ni combinacion azul+purpura
- [ ] NO `#f5f1ea` + `#b08947` (premium-consumer slop)
- [ ] NO `#0f172a` + `#3b82f6` + `#8b5cf6` (startup slop)
- [ ] NO tarjetas de 3 columnas iguales
- [ ] NO zigzag infinito de imagen-texto
- [ ] NO nombres genericos ("Hero Section", "Features", "Pricing")
- [ ] NO terminos "Elevate", "Seamless", "Revolutionary", "Game-changer"

## Stack: SvelteKit + Tailwind 4

### Layout setup:
```svelte
<!-- +layout.svelte -->
<script lang="ts">
  let { children } = $props();
</script>
{@render children()}
```

### app.css:
```css
@import "tailwindcss";
@theme {
  --font-heading: 'Geist', sans-serif;
  --font-body: 'DM Sans', sans-serif;
  --color-primary: oklch(0.55 0.15 250);
  --color-surface: oklch(0.98 0.01 250);
  --color-text: oklch(0.15 0.02 250);
  --color-error: oklch(0.55 0.2 25);
  --color-success: oklch(0.55 0.15 145);
}
```

### Import en layout:
```svelte
<!-- +layout.svelte raiz -->
<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>
{@render children()}
```

## Formato de salida

```
## UI/UX Review
- Accesibilidad: [PASS/FAIL] — {issues}
- Touch & Interaccion: [PASS/FAIL] — {issues}
- Performance: [PASS/FAIL] — {issues}
- Estilo: [PASS/FAIL] — {issues}
- Layout: [PASS/FAIL] — {issues}
- Tipografia & Color: [PASS/FAIL] — {issues}
- Animacion: [PASS/FAIL] — {issues}
- Formularios: [PASS/FAIL] — {issues}
- Navegacion: [PASS/FAIL] — {issues}
- Charts: [PASS/FAIL] — {issues}

## Anti-AI-Slop
- [PASS/FAIL] {items}

## Diseno generado
- DESIGN.md actualizado en {path}
- Paleta: {colors}
- Tipografia: {fonts}
- Estilo: {style}
```

## Tools disponibles
read_file, write_file, list_dir, shell, load_skill, spawn_subagent
