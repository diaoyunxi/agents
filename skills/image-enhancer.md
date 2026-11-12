---
name: image-enhancer
description: Improve image quality and resolution (upscale, sharpen, denoise, correct color) for photos or graphics. Use when the user asks to enhance, upscale, or clean up an image.
when_to_use: 'upscale this image', 'make it sharper / higher quality', 'enhance this photo'.
---

# Image Enhancer

Improve image quality and/or resolution for a photo or artwork.

## When to use
- "upscale this image", "make it sharper / higher quality", "enhance this photo".

## Steps
1. **Assess** — Read the source image's dimensions, format, and quality. Identify the target:
   - Upscale (resolution) — pick a factor (2×/4×) based on the use case (screen vs print at target DPI).
   - Denoise / sharpen — only if visibly degraded; avoid over-sharpening halos.
   - Color/contrast — fix exposure or white balance drift, keep the original feel.
2. **Choose a tool**
   - Python: `Pillow` for resize (use `LANCZOS` for downscale, `LANCZOS` or `BICUBIC` for upscale), `ImageEnhance` for sharpness/contrast.
   - For true upscaling (new detail), use a dedicated upscaler if available (e.g., an AI upscaler CLI or the image pipeline). Plain resize only interpolates — state that explicitly if that is all you can do.
   - Formats: keep `PNG` for graphics/text; use quality 90+ `JPEG` for photos.
3. **Apply** — Save to a new file; do not overwrite the original unless told.
4. **Verify** — Open the result, check dimensions and visual artifacts (banding, halos, compression blocking).

## Rules
- Do not claim "AI upscaling / detail restoration" if you only did interpolation.
- Preserve aspect ratio unless the user asks to crop/fit.
- Report the exact before/after pixel dimensions.

## Stop conditions
- The output meets the target size/quality, no visible artifacts, and the original is intact → stop.
