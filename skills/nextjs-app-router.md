---
name: nextjs-app-router
description: Guide Next.js 13+ App Router usage: file conventions, layouts, route handlers, server/client boundaries, and migration from Pages Router. Use when working in a Next.js project that uses (or should use) the App Router.
when_to_use: Building or migrating a Next.js 13+ project that uses `app/`. Questions about `layout.js`, `page.js`, `route.js`, server vs client, data fetching.
---

# Next.js App Router

Use the App Router conventions correctly.

## When to use
- Building or migrating a Next.js 13+ project that uses `app/`.
- Questions about `layout.js`, `page.js`, `route.js`, server vs client, data fetching.

## Core conventions
1. **File-based routing** under `app/`:
   - `page.js` → a route.
   - `layout.js` → shared wrapper; persists state across client-side navigations.
   - `loading.js` → Suspense fallback for that segment.
   - `error.js` → error boundary for that segment.
   - `not-found.js` → 404.
   - `[slug]` → dynamic segment; `[[...slugs]]` → optional catch-all; `...` → catch-all.
   - `route.js` → API/handler with `GET`/`POST`/etc. (Route Handler).
   - `template.js` → re-mounts on each navigation (use when layout state must reset).
2. **Server Components by default** — `page.js`/`layout.js` are Server Components unless `use client` is present. They can `await` directly and import from server-only packages.
3. **Client boundaries** — Add `'use client'` only where interactivity (state, event handlers, browser APIs) is required. Keep the boundary as low (deep) in the tree as possible.
4. **Data fetching** — Use `async/await` directly in Server Components. Pass down serializable props to client components. Use `use` (React 19) or context for streaming.
5. **Caching** — Understand `revalidate` and `dynamic = 'force-dynamic'`. `route.js` handlers are dynamic by default; static generation requires cache config.
6. **Middleware** — `middleware.js` at the root (or `app/`/`src/`) runs on request; can't be async with streams but can read/write headers/cookies.
7. **Streaming & Suspense** — Wrap slow data in `<Suspense>` to paint the shell first.

## Migration from Pages Router
- Port pages into `app/` with the same route.
- Move `_app.js`/`_document.js` into `layout.js`/`root-layout`.
- Replace `getServerSideProps`/`getStaticProps` with direct `async` functions in Server Components or `route.js` handlers.
- `next/image`, `next/link` work the same.

## Common mistakes
- Forgetting `'use client'` where a hook/handler is used.
- Passing non-serializable objects (e.g., `Date`, functions) from server to client props.
- Using `window`/`document` at module top level in a shared file that a server component imports.

## Stop conditions
- Routes render, server/client split is correct, and data flows without serialization errors → stop.
