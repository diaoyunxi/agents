---
name: frontend-design
description: Build production-grade UI components and styles with intentional, non-generic design. Use when the user asks to create or improve frontend UI, components, layouts, or styling.
when_to_use: Creating or improving a UI component, page, layout, or styling system.
---

# Frontend Design

Produce UI that looks intentional and human-made, not templated.

## When to use
- Creating or improving a UI component, page, layout, or styling system.

## Design principles
1. **Specificity over generic** — Avoid the default "centered hero + three feature cards + purple gradient" template. Choose a concrete visual direction from the content and audience.
2. **Establish a system early** — Pick a small set of:
   - 2-4 colors (one dominant, one accent, neutral scale).
   - 1-2 typefaces with a clear type scale (base size, heading ratio).
   - Spacing rhythm (e.g., 4px/8px increments).
   - Border-radius and elevation treatment.
3. **Hierarchy and whitespace** — Let size, weight, and spacing create hierarchy rather than borders and boxes everywhere.
4. **Interaction states** — Every interactive element needs default, hover, focus-visible, active, and disabled states. Keyboard focus must be visible.
5. **Real content** — Use plausible copy and data, not lorem ipsum, so the design can be judged in context.

## Anti-"AI-generated" constraints
- Do not use the same rounded-16px-cards-with-box-shadow on every block.
- Do not default to indigo/violet gradients for everything.
- Avoid decorative glassmorphism unless the design truly calls for it.
- Vary the composition: not every section is a 3-column grid. Use asymmetry, lists, tables, or a single strong column where appropriate.
- Match density to the product (data tool = denser, marketing page = more air).

## Implementation
- Follow the project's existing component library / design tokens if present; extend, don't fork.
- Keep components small and composable.
- Verify responsiveness at mobile, tablet, and desktop widths.
- Check accessible contrast (WCAG AA minimum).

## Stop conditions
- The UI renders in all states, is responsive, and reflects a deliberate visual system → stop.
