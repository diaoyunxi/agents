---
name: docx
description: Create and edit Word (.docx) documents with controlled formatting. Use when the user asks to generate, modify, or format a Word document.
when_to_use: 'make a Word doc', 'update this .docx', 'add a heading / table / image to the document'.
---

# Word / DOCX

Create and edit .docx documents with reliable formatting.

## When to use
- "make a Word doc", "update this .docx", "add a heading / table / image to the document".

## Tools
- Prefer the `docx_tool` extension when available (`extract_text`, `update_doc` with append/replace/structured/add_image modes).
- Otherwise use `python-docx` in a script.

## Steps
1. **Understand the target** — For an existing file, extract text/structure first to know what to preserve or replace.
2. **Build or edit** —
   - New document: set the style (Normal font, heading styles), then add content in order.
   - Update: use `append` to add to the end, `replace` to change specific text, `structured` to insert with a heading level, `add_image` for figures with optional captions.
3. **Formatting** — Use named styles (Heading 1/2/3, Normal) rather than inline ad-hoc runs so the document stays consistent. Set a readable base font/size. Use a table style for tables.
4. **Verify** — Re-open / extract text to confirm content and order are correct.

## Rules
- The output must be a valid OOXML package (a real .docx), never text or XML renamed to .docx.
- Do not claim delivery until the file is validated and registered if it is a user-facing artifact.
- Preserve the document's existing styles when editing; don't restyle the whole thing unless asked.

## Stop conditions
- The document opens, content is correct, and formatting is consistent → stop.
