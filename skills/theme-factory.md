---
name: theme-factory
description: Apply one of 10 professional design themes (color + font system) to a project, or generate a new theme as CSS design tokens. Use when the user wants a consistent, professional look applied to a site or app.
when_to_use: 'give this site/app a theme', 'make it look professional', 'apply a color/font theme'.
---

# Theme Factory

Apply a professional design theme (colors + fonts) to a project, choosing from 10 presets or generating a new one on the fly.

## When to use
- "give this site/app a theme", "make it look professional", "apply a color/font theme".

## Presets (10)
Each preset = a color system + a font pairing + a base scale. Choose by mood:
1. **Editorial** — ink-black on warm off-white, a serif display + a clean sans body. Serious, print-like.
2. **Corporate** — deep navy + neutral grays + one blue accent; a geometric sans. Trustworthy, conservative.
3. **Vibrant** — a saturated primary + 1-2 bright accents on white; a bold sans. Energetic, consumer.
4. **Minimal** — near-monochrome, one accent, generous whitespace; a single well-set sans. Calm, focused.
5. **Warm / Organic** — earth tones (terracotta, sand, olive) + a humanist sans/serif. Friendly, natural.
6. **Dark / Night** — deep charcoal base, low-saturation text, one accent; a modern sans. Tech, focus mode.
7. **Playful** — 3-4 rounded, friendly colors, a rounded sans; rounded corners. Consumer, casual.
8. **Luxury** — restrained palette (black/white/one metallic), a high-contrast serif, wide tracking. Premium.
9. **SaaS / Product** — a confident brand primary + success/warn/error neutrals, a crisp sans, 8px spacing. Clear, data-forward.
10. **Editorial Color** — off-white base + 2 complementary accents + a serif+sans mix. Confident publishing.

## Steps
1. **Pick or create the theme**
   - Pick one of the 10 presets for the mood. If none fits, generate a new theme: choose a base hue, derive an accent (complementary/analogous), build a neutral scale (10-step gray tinted with the base), and pick a font pairing (1 display + 1 body).
2. **Encode it** — Emit CSS variables (design tokens): `--color-*`, `--font-*`, `--space-*`, `--radius-*`, `--shadow-*`.
3. **Apply** — Wire the tokens into the existing component styles; replace ad-hoc hex/font values. Do not leave stray hardcoded colors.
4. **Verify** — Check contrast (WCAG AA for body text on the base), consistent spacing rhythm, and that the accent is used sparingly.

## Rules
- One accent used sparingly beats five accents used evenly.
- Token names must be semantic (`--color-bg`, `--color-text`), not raw (`#1f2937` scattered through CSS).
- Keep the change reviewable; don't rebrand the entire palette in one unreviewed commit.

## Stop conditions
- Tokens are applied, contrast passes, and no hardcoded colors remain in the touched components → stop.
