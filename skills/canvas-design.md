---
name: canvas-design
description: Create museum-grade static visual art (PDF/PNG) with embedded fonts, deliberate composition, and a mandatory self-critique pass. Use when the user asks for a poster, print, or high-quality static artwork.
when_to_use: 'make a poster / print / static artwork', 'design a piece for display', 'create a high-quality PNG/PDF art piece'.
---

# Canvas Design

Create museum-grade static visual art (PDF/PNG) with embedded fonts and a mandatory self-critique.

## When to use
- "make a poster / print / static artwork", "design a piece for display", "create a high-quality PNG/PDF art piece".

## Process
1. **Concept** — State the subject, format (A4, square, widescreen, etc.), and intended viewing context (print wall, screen, poster). Pick one dominant idea.
2. **Composition rules**
   - Establish a focal point and a clear hierarchy (what the eye hits first, second, third).
   - Use the rule of thirds / golden ratio as a starting grid, then break it deliberately if it improves the work.
   - Breath: leave intentional negative space; dense ≠ rich.
3. **Typography & color**
   - Embed fonts (no missing-glyph risk): choose 1-2 typefaces, confirm weights are available.
   - Palette: limit to a small set with a dominant tone and one accent; check contrast for legibility.
4. **Implementation** — Render via a headless browser (HTML+CSS → PNG/PDF) or a vector tool (SVG → PDF). Target print-safe resolution (300 DPI for print) or a crisp screen size.
5. **Mandatory self-critique** (do not skip)
   - Zoom in: any aliasing, misaligned elements, or font fallback?
   - Squint test: is the hierarchy readable from a distance?
   - Print check: colors in grayscale still legible? no clipping at margins (bleed)?
   - Remove anything that doesn't earn its place.
6. **Deliver** — Export both PNG (screen) and PDF (print) when the user wants print; embed all fonts in the PDF.

## Rules
- No floating stock imagery; all assets must be coherent with the concept.
- The critique pass is required; "looks fine at first glance" is not a pass.

## Stop conditions
- Output renders at the target resolution, fonts are embedded, and the self-critique found no unresolved issues → stop.
