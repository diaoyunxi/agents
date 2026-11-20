---
name: react-server-components
description: Apply React Server Components patterns: where to render on the server vs client, async data fetching, shared files, and serializable prop boundaries. Use when building React/Next.js features and deciding how to split server and client work.
when_to_use: Deciding where a component/data-fetch belongs in React 18/19 + Next.js. Hitting 'Component 'X' does not use the `hooks`...' or non-serializable props errors.
---

# React Server Components

Split rendering work between server and client correctly.

## When to use
- Deciding where a component/data-fetch belongs in React 18/19 + Next.js.
- Hitting "Component 'X' does not use the `hooks`..." or non-serializable props errors.

## Rules
1. **Default to server** — A component is a Server Component unless it has interactivity. Only add `'use client'` when you need `useState`/`useEffect`/event handlers/browser APIs.
2. **Server components can** `async/await` directly to fetch data and can import server-only code.
3. **Client components cannot** — They receive serializable props from the server. No functions, `Date` objects, or Map/Set in props.
4. **Keep the boundary deep** — Put `'use client'` on the smallest leaf that needs interactivity; keep large trees on the server so they don't ship to the browser.
5. **Shared files** — A file without `'use client'` is server-only. A file with `'use client'` is a client boundary and its imports must be usable on the client.
6. **Async components** (React 19) — Can `return await` inside Server Components; use Suspense to stream.

## Data flow
- Fetch in a Server Component, pass plain data down.
- For interactive needs, pass a `useOptimistic`/`useActionState`-compatible setup or expose an action (a function) via `use server`.

## Common mistakes
- Adding `'use client'` to a whole page "just in case".
- Passing a `Date` from server → client (serialize to ISO string).
- Importing a server-only package (DB driver, env secrets) inside a client component.

## Stop conditions
- No serialization errors, interactivity works, and the client bundle is as small as it should be → stop.
