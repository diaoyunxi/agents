---
name: llm-application-dev
description: Build LLM-driven applications: prompt engineering, structured output, tool/function calling, retrieval, and reliable integration patterns. Use when adding or improving AI features into a product.
when_to_use: Adding chat, generation, classification, extraction, RAG, or agents.
---

# LLM Application Development

Build reliable LLM features, not just "call the model".

## When to use
- Adding chat, generation, classification, extraction, RAG, or agents.

## Core patterns
1. **Structured output** — Ask for and enforce a schema (JSON mode / structured outputs / tool-defined shapes). Validate before use.
2. **Prompt engineering**
   - Put system instructions, then few-shot examples, then the user input.
   - Give the model a role, constraints, and the exact output format.
   - Separate the static prompt from dynamic data to enable caching.
   - Keep it terse; "do X, return JSON with fields a,b,c" beats paragraphs of tone.
3. **Retrieval (RAG)**
   - Chunk with overlap; embed with a current model; store in a vector store.
   - Hybrid retrieval (keyword + vector) beats vector-only for many workloads.
   - Rerank top-k; inject only the top passages to control cost and latency.
   - Always cite the source passage in the answer.
4. **Tool / function calling**
   - Define tools with precise JSON schemas and clear descriptions.
   - Validate returned arguments before executing.
   - Bound the loop: max iterations, timeout, and a fallback when the model gets stuck.
5. **Reliability**
   - Temperature: low (0-0.2) for extraction/classification; higher only for creative tasks.
   - Retry with backoff on 429/5xx; cache deterministic results.
   - Add a guardrail step (length, PII, refusal) when the output reaches users.

## Integration checklist
- Stream for long outputs; show progress.
- Log prompts, outputs, tokens, latency, and cost per call (anonymize).
- Make the model/params a config, not a hardcoded string.
- Provide a deterministic fallback path if the provider is unavailable.

## Stop conditions
- Output validates against the schema, latency/cost are within budget, and failure paths degrade gracefully → stop.
