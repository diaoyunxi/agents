---
name: mcp-builder
description: Build, test, and evaluate a Model Context Protocol (MCP) server: research the target, implement tools/resources/prompts, and verify. Use when creating or extending an MCP server.
when_to_use: Creating a new MCP server or adding a tool/resource/prompt to one.
---

# MCP Builder

Build and verify a Model Context Protocol server.

## When to use
- Creating a new MCP server or adding a tool/resource/prompt to one.

## Steps
1. **Research → scope** — Identify exactly what capability the MCP should expose. Define a small set of tools (each with a clear name, description, and input schema). Avoid dumping an entire SDK as one tool.
2. **Design the tools**
   - Name: verb-first, specific (`fetch_issue`, `create_report`).
   - Description: one line, states when to use it.
   - Inputs: JSON Schema, minimal required fields, documented defaults.
   - Outputs: structured, predictable. Return errors as values with a `success`/`error` shape, not only exceptions.
3. **Implement**
   - Follow the MCP SDK transport (stdio or HTTP). Register tools/resources/prompts correctly.
   - Keep handlers thin: parse → validate → call the underlying API/service → serialize the result.
   - No secrets in code; read from env/config.
   - Add timeouts and bounded retries for external calls.
4. **Test**
   - Unit-test each tool's happy path, validation failure, and error path.
   - Run the server and confirm a client lists the tools and can invoke them.
   - Confirm tool descriptions are good enough that a model picks the right one.
5. **Evaluate** — Check: do tool names/descriptions disambiguate? Are outputs useful without extra round-trips? Is the surface area minimal?

## Rules
- Prefer fewer, well-described tools over many fuzzy ones.
- Idempotent tools where possible; clearly mark destructive ones.

## Stop conditions
- Tools list correctly, each passes its tests, and a representative model call works → stop.
