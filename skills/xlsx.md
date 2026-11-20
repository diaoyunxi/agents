---
name: xlsx
description: Process Excel (.xlsx) spreadsheets: read, analyze, and modify data, with financial-modeling standards and formula analysis. Use when the user asks to work with a spreadsheet.
when_to_use: 'analyze this spreadsheet', 'add a column / formula', 'summarize the data', 'build a financial model'.
---

# Excel / XLSX

Read and manipulate .xlsx workbooks reliably.

## When to use
- "analyze this spreadsheet", "add a column / formula", "summarize the data", "build a financial model".

## Tools
- Prefer the `xlsx_tool` extension when available (list_worksheets, get_columns, get_range, find_text, update_cell, save).
- Otherwise use `openpyxl` (formula-aware) or `pandas` for bulk data.

## Steps
1. **Inspect** — List worksheets; read the header row(s) to learn the schema; check a sample of the data range.
2. **Analyze / modify**
   - For data questions, compute with the appropriate range; state the range used.
   - When writing formulas, use absolute/relative references deliberately (`$A$1` vs `A1`).
   - Prefer writing values that are computed in the sheet (formulas) over hardcoding when the user wants a live model.
3. **Financial-modeling standards** (when applicable)
   - Separate inputs (hard-coded, colored e.g. blue) from formulas (no hard-coded numbers inside formula logic).
   - One model = one currency/unit; label every assumption.
   - Avoid volatile functions (`OFFSET`, `INDIRECT`, `TODAY`) unless required.
   - Use consistent sign conventions for cash flows; document them.
4. **Verify** — After saving, re-read changed ranges to confirm values and formulas.

## Rules
- Always save to a new file or the confirmed target; never corrupt the input.
- Report any cell that was out of range, read-only-protected, or containing a circular reference.
- Numbers stay numbers (not text); dates stay real dates.

## Stop conditions
- The sheet is updated/analyzed as requested and re-read verification passes → stop.
