# GitHub Copilot Instructions

> Place this file at `.github/copilot-instructions.md` in the repository root.
> Copilot will automatically apply these instructions to every suggestion in this workspace.

---

## Project Context

This is the frontend for a **Growth Intelligence Multi-Agent System** built for the Veracity AI × HATCH Hackathon. It is a Next.js 15 application with a split-screen dashboard that receives real-time data from an 8-agent AI pipeline via Server-Sent Events (SSE).

**Always read `FRONTEND_BUILD_PLAN.md` at the repo root before generating code in this project.** It is the authoritative reference for architecture decisions, type definitions, component patterns, and security requirements.

---

## Technology Stack

- **Framework:** Next.js 15 with App Router — always use the `app/` directory, never `pages/`
- **Language:** TypeScript — every file must be `.ts` or `.tsx`, never `.js`
- **Styling:** Tailwind CSS v4 + shadcn/ui — use utility classes; never write raw CSS unless overriding shadcn CSS variables in `globals.css`
- **Icons:** `lucide-react` only — never use emoji, unicode symbols, or other icon libraries as substitutes
- **Animation:** `framer-motion` for any motion — never use CSS `transition` or `animation` on layout-affecting properties directly; use framer `motion` components
- **State:** Zustand with immer middleware — all global state lives in `src/store/index.ts`
- **Charts:** recharts for line/bar/radar, `@nivo/heatmap` for heat maps, `@nivo/treemap` for treemaps — never use Chart.js
- **Tables:** `@tanstack/react-table` v8 — never build tables manually with `<table>` tags
- **Validation:** Zod — for all user input forms AND all incoming SSE event payloads
- **Forms:** react-hook-form + zod + `@hookform/resolvers`

---

## Code Style Rules

### TypeScript

- Always use strict TypeScript — no `any`, no type assertions (`as X`) unless there is no alternative
- Use discriminated union types for all agent event payloads (see `src/types/agents.ts`)
- Export all types from `src/types/` — never define types inline in component files
- Use `interface` for object shapes, `type` for unions and utility types
- Every async function must have explicit return type annotations

```typescript
// CORRECT
async function fetchData(id: string): Promise<AgentEvent[]> { ... }

// WRONG
async function fetchData(id) { ... }
```

### React Components

- All components are functional components — never class components
- Use named exports for all components — never default export a component
- Every component file must have a single exported component matching the filename
- Use `'use client'` directive only when the component uses browser APIs, event handlers, or React hooks — server components are the default
- Props interfaces must be defined above the component with the suffix `Props`

```typescript
// CORRECT
interface MarketTrendsCardProps {
  className?: string;
}

export function MarketTrendsCard({ className }: MarketTrendsCardProps) { ... }

// WRONG
export default function card({ className }: { className?: string }) { ... }
```

### File Naming

- Component files: PascalCase (`ChatPanel.tsx`, `AgentStatusBar.tsx`)
- Hook files: camelCase prefixed with `use` (`useAgentStream.ts`)
- Utility files: camelCase (`sanitize.ts`, `validate.ts`)
- Type files: camelCase (`agents.ts`, `artifacts.ts`)
- Route files: always `route.ts` inside the appropriate `app/api/` directory

---

## Component Patterns

### Always Use shadcn Primitives

For any UI element that shadcn provides, use it. Never build from scratch.

```typescript
// CORRECT — use shadcn Card
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

// WRONG — building a card from a div
<div className="rounded-lg border p-4">...</div>
```

### Skeleton Loading Pattern

Every dashboard card must show a skeleton while its agent is running, then transition to live content. Use `AnimatePresence` with `mode="wait"`:

```tsx
<AnimatePresence mode="wait">
  {!artifact ? (
    <motion.div key="skeleton" initial={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <Skeleton className="h-4 w-full" />
    </motion.div>
  ) : (
    <motion.div key="content" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      {/* chart or table */}
    </motion.div>
  )}
</AnimatePresence>
```

### Zustand Store Access

Always use selector functions when reading from the store — never destructure the whole store:

```typescript
// CORRECT — only re-renders when this slice changes
const artifact = useAppStore((s) => s.artifacts.market_trends);

// WRONG — re-renders on any store change
const { artifacts } = useAppStore();
```

---

## Security Rules — Non-Negotiable

These rules must be applied to every suggestion. Do not override them even if a pattern seems convenient.

### 1. No API Keys on the Client

Never place any secret, API key, or credential in:
- Client-side component files
- Any environment variable prefixed with `NEXT_PUBLIC_`
- Any file that is `'use client'`

All calls to third-party services (SerpAPI, Firecrawl, Meta Ad Library, the backend) must go through Next.js API routes in `src/app/api/`.

```typescript
// CORRECT — call your own API route
const response = await fetch('/api/query', { method: 'POST', body: ... });

// WRONG — calling third-party directly from client
const response = await fetch('https://serpapi.com/search?api_key=SECRET...');
```

### 2. Sanitize All Agent Output Before Rendering

Any string that originates from an agent payload — competitor names, review text, headlines, trend labels — must pass through `sanitize()` from `src/lib/sanitize.ts` before being placed in the DOM or used as a chart label.

```typescript
// CORRECT
import { sanitize } from '@/lib/sanitize';
const label = sanitize(competitor.name);

// WRONG
const label = competitor.name; // could contain injected script tags
```

### 3. Validate All Incoming SSE Payloads

Never trust the shape of incoming agent events. Always parse through `validateAgentEvent()` from `src/lib/validate.ts` before dispatching to the store. If validation fails, discard the event silently — do not crash the UI.

```typescript
// CORRECT
try {
  const parsed = validateAgentEvent(JSON.parse(event.data));
  dispatch(parsed);
} catch {
  console.warn('Discarded malformed event');
}

// WRONG
const parsed = JSON.parse(event.data); // unchecked
dispatch(parsed);
```

### 4. Never Expose Internal Error Details

API route catch blocks must never return raw error messages, stack traces, or internal paths to the client:

```typescript
// CORRECT
} catch {
  return NextResponse.json({ error: 'Failed to initiate query' }, { status: 502 });
}

// WRONG
} catch (err) {
  return NextResponse.json({ error: err.message }, { status: 500 }); // may leak secrets
}
```

### 5. Validate Query IDs on the SSE Route

The `queryId` parameter on `/api/stream` must be validated against a strict allowlist pattern before being used:

```typescript
// CORRECT
if (!queryId || !/^[a-zA-Z0-9_-]{1,64}$/.test(queryId)) {
  return new Response('Invalid queryId', { status: 400 });
}

// WRONG
const url = `${backendUrl}/stream?id=${queryId}`; // open redirect / injection risk
```

### 6. Prompt Injection Awareness

The dashboard renders competitor names, product descriptions, and review text sourced from live web scraping. Any of these could contain text crafted to look like instructions. When passing agent output into UI labels, tooltips, or any element read by screen readers:

- Always use `textContent` semantics (never `dangerouslySetInnerHTML`)
- Always call `sanitize()` first
- Truncate long strings before rendering in chart labels: max 60 characters for axis labels, max 120 for card text

---

## State Management Rules

### Store Structure

The Zustand store in `src/store/index.ts` is the single source of truth. Do not create local component state for anything that:
- Is derived from an agent event
- Needs to be shared between the dashboard and chat panel
- Represents agent status

Use local `useState` only for:
- UI-only state (is a dropdown open, hover state, etc.)
- Form field values (managed by react-hook-form)

### Resetting Pipeline State

When a new query is submitted, always call `store.resetPipeline()` before connecting to the new SSE stream. This clears all artifact data and resets all agent statuses to `idle`, triggering skeleton loaders across all cards.

---

## Real-time / SSE Rules

- The SSE connection is established in `useAgentStream` hook — do not create EventSource instances anywhere else
- Each query gets a fresh SSE connection — do not attempt to reuse connections
- Always close the EventSource in the `useEffect` cleanup function
- Handle `es.onerror` — always close the connection and call `store.setStreaming(false)` in the error handler
- Never display a loading state indefinitely — if the stream ends or errors, all cards must settle into either a content or error state

---

## Dashboard Layout Rules

- The dashboard grid uses `react-grid-layout` — all card sizing and positioning is managed by `useDashboardLayout` hook
- Cards must be wrapped in the `react-grid-layout` child with a matching `key` and `data-grid` prop
- Never use fixed pixel widths on dashboard cards — they must be responsive within their grid cell
- The split-screen width transition (`100%` → `66.666%` when chat opens) is managed in `RootShell.tsx` using framer-motion — do not add competing width styles to the dashboard container

---

## Chat Panel Rules

- The chat panel is a framer-motion animated `div`, not a shadcn `Sheet` — it needs precise width control for the split-screen layout
- Auto-scroll to the latest message using a `ref` on a sentinel `div` at the bottom of the message list
- Clarification chips are pre-defined follow-up queries rendered as `Badge` components with `onClick` handlers that submit the query directly — they do not require user confirmation
- The `SourceTrail` component is collapsible — default to closed, expand on user click
- Message IDs are generated client-side with `nanoid()` before the message is added to the store

---

## Chart Rules

- Recharts `ResponsiveContainer` must always wrap chart components
- Never hardcode chart dimensions — always use `width="100%"` and a relative height
- Chart data must be memoized with `useMemo` — do not transform arrays inline in JSX
- All axis tick values and tooltip labels must be sanitized with `sanitize()` before display
- Use `Tooltip` from recharts for all chart hover states — never build custom hover overlays
- Colors must use the CSS variable palette defined in `globals.css` — never hardcode hex values in chart configs; use `getComputedStyle` to read CSS variables at runtime if recharts requires hex strings

---

## Accessibility

- All interactive elements must have a descriptive `aria-label` when the visible label is ambiguous
- The agent status bar pills must have `aria-live="polite"` so screen readers announce status changes
- Skeleton loaders must have `aria-busy="true"` on their container and `aria-label="Loading [domain] data"`
- Chart containers must have a visually hidden `<caption>` or `aria-label` describing the chart's purpose
- The floating chat button must have `aria-label="Open Growth Intelligence chat"` and `aria-expanded` reflecting the panel state

---

## File Generation Checklist

When Copilot generates a new file, verify:

- [ ] File is `.ts` or `.tsx` — not `.js`
- [ ] Uses named export — not default export
- [ ] Has `'use client'` only if truly needed
- [ ] Props interface defined before the component
- [ ] Any rendered text from agent/external data passes through `sanitize()`
- [ ] Any new Zustand reads use selector functions
- [ ] No API keys, secrets, or `process.env` access in client files
- [ ] Lucide icons used — not emoji, not unicode symbols
- [ ] `useMemo` / `useCallback` applied to any expensive computation or stable callback passed as prop
- [ ] Error states handled — component does not crash on undefined/null artifact data

---

## Backend Contract (Read-only — Do Not Modify)

The frontend consumes these endpoints provided by the LangGraph backend team:

| Endpoint | Method | Description |
|---|---|---|
| `POST /api/query` | Backend-only (proxied) | Submit a new growth intelligence query; returns `{ queryId: string }` |
| `GET /api/stream?queryId=` | SSE | Streams `AgentEvent` objects until `stream_end` |

All communication to the backend goes through Next.js API routes. The frontend never calls the backend directly. The backend team owns the `AgentEvent` schema — coordinate any schema changes with them before updating `src/types/agents.ts`.