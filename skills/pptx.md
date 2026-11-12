---
name: pptx
description: Create and edit PowerPoint (.pptx) slide decks, with a mandatory adversarial QA pass before delivery. Use when the user asks to generate, modify, or review a slide deck.
when_to_use: 'make a slide deck', 'turn this into PPTX', 'add a slide'.
---

# PowerPoint / PPTX

Create and edit .pptx slide decks with a mandatory adversarial QA pass.

## When to use
- "make a slide deck", "turn this into PPTX", "add a slide".

## Build
- Prefer the `pptx_tool` extension when available; otherwise use `python-pptx`.
- **Slide layout discipline**
  - One idea per slide. Title + a few bullets or one strong visual, not a wall of text.
  - Set a consistent template: master slide, accent color, and 1-2 fonts.
  - Headings: short (≤8 words). Body: bullet lines ≤ ~15 words.
  - Provide a title slide, an agenda, and a closing/next-steps slide.
- **Content** — Source every factual claim; keep numbers in speaker notes with their source.
- **Images/charts** — Use real data for charts; caption images; avoid stock-photo clichés.

## Mandatory adversarial QA
Before declaring the deck done, run a self-review that actively hunts for failure:
1. **Overflow** — Does any text box or bullet list exceed the slide? Check at the intended 16:9 / 4:3 ratio.
2. **Overlap** — Do shapes, captions, or footers collide?
3. **Contrast** — Is text readable against the background (light-on-light, dark-on-dark)?
4. **Consistency** — Are fonts, sizes, and colors used uniformly across slides?
5. **Broken references** — Any missing images, blank slides, or placeholder "lorem" left in?
6. **Order** — Does the narrative flow (context → problem → solution → evidence → ask)?
Fix every finding, then re-open the file and confirm it renders.

## Rules
- The output must be a valid OOXML package, never XML/HTML renamed to .pptx.
- Do not claim delivery until the QA pass is complete and the file validates.

## Stop conditions
- All slides render cleanly and every QA category is clear → stop.
