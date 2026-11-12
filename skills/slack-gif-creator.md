---
name: slack-gif-creator
description: Generate small, looping, Slack-appropriate animated GIFs (reactions, status, or share) with correct size, frame, and palette constraints. Use when the user asks for a Slack GIF or animated emoji.
when_to_use: 'make a Slack GIF / animated emoji', 'create a small looping animation for Slack'.
---

# Slack GIF Creator

Generate animated GIFs suitable for Slack (emoji/reactions, channel status, or shared animation).

## When to use
- "make a Slack GIF / animated emoji", "create a small looping animation for Slack".

## Constraints (Slack)
- Target size: keep under 50 MB (Slack limit for custom GIFs) and small file in practice (ideally < 2 MB for quick reactions).
- Dimensions: small, e.g., 120×120 to 240×240 px; reactions look better small and centered.
- Loop: seamless infinite loop; short (0.5–2 s loop is typical).
- Frames: 8–30 fps; 12–24 frames for a smooth but compact loop.
- Colors: limit the palette to keep the file small.

## Process
1. **Concept** — One clear, legible action at small size. If it's not readable at ~48 px, it will not work in Slack.
2. **Build**
   - p5.js / canvas / SVG animation → capture frames.
   - Or Python (Pillow / imageio) to assemble frames into a GIF.
3. **Assemble** — Set frame delay, optimize: reduce frames, shrink, and quantize colors (≤256). Use `GIFSKY`-style or `gifsicle` to compress.
4. **Verify** — Confirm file size, loop is seamless, and it stays legible when scaled down.

## Tools
- Python: `Pillow` (save GIF with `save_all`), `imageio`, `gifsicle` for post-optimization.
- Browser: p5.js to author, then capture frames to build the GIF.

## Rules
- Center the subject with margin so Slack's small crop does not clip it.
- No text unless it is the point; tiny text is unreadable.
- Confirm the final file is a valid, looping GIF and report its size.

## Stop conditions
- GIF loops cleanly, is legible at small size, and is under Slack's size limit → stop.
