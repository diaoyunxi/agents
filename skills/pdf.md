---
name: pdf
description: Read, merge, split, watermark, fill forms in, and OCR PDF files. Use when the user asks to process, convert, or extract content from a PDF.
when_to_use: 'merge these PDFs', 'extract text from this PDF', 'fill the form', 'add a watermark', 'OCR this scanned document'.
---

# PDF Processing

Read and manipulate PDF files reliably.

## When to use
- "merge these PDFs", "extract text from this PDF", "fill the form", "add a watermark", "OCR this scanned document".

## Read / extract
- **Text extraction** — Use a PDF text library (e.g., `pypdf`, `pdfplumber`, `pdftotext`). `pdfplumber` gives better table/layout fidelity; `pdftotext -layout` preserves columns.
- **Tables** — Use `pdfplumber` table extraction; verify against the rendered page.
- **Scanned (no text layer)** — Run OCR first (e.g., `tesseract` via `ocrmypdf`), then extract text.
- **Images** — Extract embedded images with `pypdf` or `pdfimages`.

## Manipulate
- **Merge/split** — `pypdf` (Python) for page-level ops. Split by page range; merge in the user's stated order.
- **Rotate / crop** — `pypdf` supports `rotate` and `cropBox`.
- **Watermark** — Create a single-page watermark PDF (text or image, semi-transparent), then `merge_page` over every page; save as a new file, never destroy the original unless told to.
- **Fill forms** — Detect AcroForm fields (`get_fields()`), set values, and flatten if the user wants the form non-editable. Verify which fields were found; report any the form does not expose.
- **Compress** — Re-save with lower image quality / `ghostscript` (`-dPDFSETTINGS=/ebook`) to reduce size.

## Rules
- Always write to a new output file; do not overwrite the input unless the user explicitly says so.
- Preserve original text exactly on extraction — do not paraphrase or drop pages.
- For password-protected PDFs, ask for the password; do not attempt to break encryption.

## Stop conditions
- The requested operation is complete and the output file opens/reads correctly → stop. Report any pages or fields that could not be processed.
