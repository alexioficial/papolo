---
name: ux-methodology
description: Metodologia de diseno UX — user flows, wireframes, estados, accesibilidad, micro-interacciones. Cargala antes de implementar UI para planificar la experiencia de usuario completa, no solo el aspecto visual.
---

# Skill: Metodologia UX

## Cuando usarla
- Antes de implementar cualquier UI con interaccion de usuario
- Cuando el sistema tiene formularios, flujos multi-paso, dashboards, o pages con estado
- Cuando el planner/sveltekit-expert no cubrio los flujos de UX
- Para features con validacion, errores, casos vacios

## Cuando NO usarla
- APIs, backends, scripts, sistemas sin UI
- Landing pages simples de una sola seccion

## Procedimiento

### Fase 1: User Flows

Antes de escribir codigo, mapea el flujo completo del usuario:

```
Ej: Sistema de inventario
1. Usuario abre app → ve login
2. Login OK → redirige a dashboard con resumen
3. Click "Agregar producto" → formulario con campos (nombre, SKU, precio, stock)
4. Submit OK → vuelve a lista con producto nuevo
5. Submit con error → errores inline en cada campo
6. Click "Eliminar" → confirmacion modal → si confirma, borra y refresca lista
7. Sin productos → empty state con CTA "Agregar primer producto"
```

Para cada pantalla del flujo, identifica:

| Pantalla | Rol | Input | Accion | Output | Error | Empty |
|----------|-----|-------|--------|--------|-------|-------|
| Login | todos | email+pass | submit | dashboard | "credenciales invalidas" | N/A |
| Dashboard | admin | N/A | ver resumen | cards con stats | error al cargar | "no hay datos" |
| Crear producto | admin | form | submit | redirect a lista | errores por campo | N/A |
| Lista productos | todos | N/A | ver tabla | tabla paginada | error carga | "no hay productos" |

### Fase 2: Estados por Componente

Para CADA componente que muestra datos, define:

```
Componente: ProductList
┌──────────────────────────────────────┐
│  Loading State:                      │
│  ┌──┐ ┌──┐ ┌──┐                     │
│  │SK│ │SK│ │SK│  ← skeleton cards   │
│  └──┘ └──┘ └──┘                     │
├──────────────────────────────────────┤
│  Empty State:                        │
│  [icono]                             │
│  No hay productos                    │
│  [Agregar primer producto] ← botón   │
├──────────────────────────────────────┤
│  Error State:                        │
│  ⚠ Error al cargar productos        │
│  [Reintentar] ← botón                │
├──────────────────────────────────────┤
│  Success State:                      │
│  Producto A    $10    50 en stock    │
│  Producto B    $20    3 en stock     │
│  Producto C    $5     0 en stock ⚠  │
│  ← [Anterior]   Página 1 de 3  [Siguiente] → │
└──────────────────────────────────────┘
```

### Fase 3: Formularios (Reglas de UX)

Todo formulario debe tener:

1. **Validacion client-side** (instantanea, antes de submit):
   - Campos requeridos marcados con `*`
   - Formato validado on-blur o on-input
   - Mensajes de error debajo del campo

2. **Validacion server-side** (post-submit):
   - Mismos checks + seguridad (no confiar en client)
   - Errores estructurados vinculados a campos

3. **Feedback visual**:
   - Submit button: estado "enviando..." (disabled + spinner)
   - Success: mensaje breve + redirect o limpiar form
   - Error: errores inline + scroll al primer error

4. **Prevencion de doble submit**:
   - Deshabilitar boton despues del primer click
   - Re-habilitar solo si hay error

5. **Confirmacion en acciones destructivas**:
   - Modal: "¿Seguro que queres eliminar X?"
   - Boton de confirmacion rojo, boton cancelar
   - TTL por si el usuario se distrae

### Fase 4: Navegacion y Layout

- **Breadcrumbs** para paginas anidadas (Productos > Editar "Zapatos")
- **Sidebar o navbar** con seccion activa resaltada
- **Back button** en formularios de edicion/creacion
- **404 page** personalizada con link a home
- **Loading states** entre paginas (SvelteKit `nprogress` o transition)

### Fase 5: Accesibilidad (WCAG 2.1 AA minimo)

Checklist obligatorio en toda UI:

- [ ] Todo elemento interactivo es accesible por teclado (Tab, Enter, Escape)
- [ ] Botones icono tienen `aria-label`
- [ ] Form inputs tienen `<label>` asociado
- [ ] Mensajes de error en forms tienen `role="alert"`
- [ ] Color no es el unico indicador de estado (texto + icono + color)
- [ ] Contraste de color: 4.5:1 texto normal, 3:1 texto grande
- [ ] Navegacion por landmarks (`<nav>`, `<main>`, `<aside>`)
- [ ] Skip to content link
- [ ] Focus visible en todos los elementos interactivos
- [ ] Modales: focus trap + Escape para cerrar + `aria-modal`
- [ ] `prefers-reduced-motion` respetado (desactivar animaciones)

```svelte
<script lang="ts">
  let { onConfirm, onCancel, title, message }: {
    onConfirm: () => void;
    onCancel: () => void;
    title: string;
    message: string;
  } = $props();
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  role="dialog"
  aria-modal="true"
  aria-labelledby="modal-title"
  onkeydown={(e) => e.key === 'Escape' && onCancel()}
  use:focusTrap
>
  <h2 id="modal-title">{title}</h2>
  <p>{message}</p>
  <button onclick={onCancel}>Cancelar</button>
  <button onclick={onConfirm} class="btn-danger">Confirmar</button>
</div>
```

### Fase 6: Micro-Interacciones

Detalles que separan una UI profesional de una generica:

- **Hover states**: botones cambian de tonalidad, links subrayados
- **Focus rings**: `outline` visible en todos los elementos focuseables (nunca `outline: none` sin alternativa)
- **Transitions**: `transition: colors 150ms` en botones, `transition: transform 200ms` en cards hover
- **Page transitions**: SvelteKit `beforeNavigate` para transiciones, `transition:fade` en elementos
- **Loading spinners**: pulsantes honestos, no animaciones infinitas sin feedback
- **Scroll behavior**: `scroll-behavior: smooth` en anchor links
- **Optimistic updates**: en UI con React Query / Svelte, actualizar antes de confirmacion server

### Fase 7: Responsive Mobile

- **Touch targets**: minimo 44x44px para botones y links
- **Forms mobile**: inputs sin zoom raro (`font-size: 16px` minimo), botones full-width
- **Tables responsive**: horizontal scroll o card view en mobile
- **Nav mobile**: hamburger menu o bottom navigation
- **No hover-dependent features**: tooltips y dropdowns deben funcionar en touch

## Implementacion en SvelteKit

### Estructura de formulario con validacion:

```svelte
<script lang="ts">
  let { form, errors }: { form: import('./$types').ActionData; errors: Record<string, string> } = $props();

  let name = $state(form?.data?.name ?? '');
  let price = $state(form?.data?.price ?? '');
  let nameError = $derived(errors?.name ?? '');
  let priceError = $derived(errors?.price ?? '');
  let submitting = $state(false);
</script>

<form method="POST" use:enhance={() => { submitting = true; return async () => { submitting = false; }}}>
  <label for="name">Nombre del producto *</label>
  <input id="name" name="name" bind:value={name} aria-invalid={!!nameError} aria-describedby={nameError ? 'name-error' : undefined} />
  {#if nameError}
    <p id="name-error" role="alert" class="text-red-500 text-sm">{nameError}</p>
  {/if}

  <label for="price">Precio *</label>
  <input id="price" name="price" type="number" step="0.01" bind:value={price} aria-invalid={!!priceError} />
  {#if priceError}
    <p id="price-error" role="alert" class="text-red-500 text-sm">{priceError}</p>
  {/if}

  <button type="submit" disabled={submitting}>
    {#if submitting}
      <span class="spinner" aria-hidden="true"></span> Guardando...
    {:else}
      Guardar producto
    {/if}
  </button>
</form>
```

## Formato de salida

```
## User Flows
- {descripcion del flujo completo}

## Estado por componente
- {componente}: {loading | empty | error | success}

## Formularios
- {formulario}: {campos, validaciones, feedback}

## Checklist accesibilidad
- [PASS/FAIL] Keyboard nav
- [PASS/FAIL] ARIA labels
- [PASS/FAIL] Contraste
- [PASS/FAIL] Focus management
- [PASS/FAIL] Reduced motion

## Implementacion
- {archivos modificados}
```

## Tools disponibles
read_file, write_file, list_dir, shell, load_skill, spawn_subagent
