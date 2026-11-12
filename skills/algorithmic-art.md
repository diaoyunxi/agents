---
name: algorithmic-art
description: Generate p5.js generative/algorithmic art through a philosophy-first process, delivered as a self-contained HTML file. Use when the user asks for generative art, creative coding, or a p5.js piece.
when_to_use: 'make a generative art piece', 'create some algorithmic / p5.js art', 'visual generative work'.
---

# Algorithmic Art

Generate p5.js generative art via a "philosophy first, expression second" process, outputting a self-contained HTML file.

## When to use
- "make a generative art piece", "create some algorithmic / p5.js art", "visual generative work".

## Process
1. **Philosophy first** — Before any code, state the work's intention in 2-3 sentences: what does it explore (order vs chaos, emergence, rhythm, decay)? This is the north star for every parameter.
2. **Choose a visual system**
   - Motion: particle fields, L-systems, flow fields, cellular automata, spirographs, recursive subdivision.
   - Palette: 2-5 colors with a deliberate harmony (analogous, complementary, or monochromatic + accent).
   - Composition: where the eye should land; negative space matters.
   - Constraints: a limit (few colors, one shape, fixed grid) makes the work stronger, not weaker.
3. **Implement in p5.js**
   - A single self-contained HTML file: inline the p5.js from CDN, no build step, opens directly in a browser.
   - Expose a few knobs (count, seed, speed, color) so the piece can be re-seeded.
   - Use a fixed random seed for reproducibility; show the seed in a caption.
   - Run at a reasonable FPS; pause or stop animation on a "finished" state if it is a still.
4. **Self-critique** — Render it, then judge against the philosophy: Does it look intentional or accidental-messy? Is there hierarchy? Would a curator describe it in one clear sentence? Iterate parameters, don't just ship.
5. **Deliver** — Save the HTML file; include a short artist's statement (the philosophy) with it.

## Rules
- One file, self-contained, no external assets except the p5.js CDN.
- Reproducible: a known seed regenerates the same piece.
- No placeholder "lorem art"; the composition must be deliberate.

## Stop conditions
- The piece renders, matches its stated philosophy, and is reproducible by seed → stop.
