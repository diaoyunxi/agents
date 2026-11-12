---
name: backend-development
description: Design and implement server-side components: REST/GraphQL APIs, database access, service architecture, validation, and error handling. Use when building or extending a backend service.
when_to_use: Adding an API endpoint, a data model, a background job, or a service.
---

# Backend Development

Build and extend a server-side service with clear contracts and safe data handling.

## When to use
- Adding an API endpoint, a data model, a background job, or a service.

## Steps
1. **Contract first** — Define the API shape (method, path, request/response schema, status codes, error shape). Match the project's existing conventions.
2. **Layering** — Keep a thin transport layer (handler), a service/use-case layer, and a data-access layer. No business logic in the handler; no HTTP concerns in the data layer.
3. **Validation** — Validate all input at the edge. Reject early with clear 400 responses. Use the project's validator (e.g., a schema lib), not ad-hoc checks.
4. **Data access** — Parameterized queries only. Map to models at the boundary. Handle NOT FOUND vs forbidden distinctly (404 vs 403).
5. **Error handling** — Define error types; convert them to consistent JSON errors. Do not leak stack traces or internals. Log with context (request id).
6. **Idempotency & concurrency** — For mutating endpoints, consider idempotency keys and safe retries. Use transactions where multi-step writes must be atomic.
7. **AuthN/AuthZ** — Enforce authentication, then per-resource authorization, in every handler. Fail closed.
8. **Observability** — Structured logs, request ids, health/readiness endpoints.

## Rules
- Never trust client-supplied ids when a user can only see their own data.
- Keep secrets out of code; load from env/secret manager.
- Write tests for the service layer and for the error paths, not just the happy path.

## Stop conditions
- Endpoints behave per the contract, validation and error paths are covered, authz is enforced → stop.
