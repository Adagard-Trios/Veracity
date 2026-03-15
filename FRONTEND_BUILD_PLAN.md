# Growth Intelligence Platform — Frontend Build Plan

> **Hackathon:** Veracity AI × HATCH · 15 March 2026
> **Role:** Frontend Developer
> **Stack:** Next.js 15, TypeScript, Shadcn/UI, Framer Motion
> **Time budget:** ~6.5 hours build + 30 min demo prep

---

## System Overview

An 8-agent growth intelligence system that delivers boardroom-quality competitive insights in minutes. The frontend is a split-screen dashboard where:

- **Left (2/3):** Live dashboard with cards, charts, tables, and dynamic artifacts — all updating in real-time as agents complete their work
- **Right (1/3):** A floating chat button that slides in a conversational interface; as the user converses, the dashboard artifacts update to reflect new context

The 8-agent backend pipeline:

```
Agent 1 (Information Fetcher)
    ↓ parallel dispatch
Agents 2–7 (6 Domain Specialists — run in parallel)
    ↓ converge
Agent 8 (Compiler — synthesis + confidence scoring)
    ↓
WebSocket / SSE Stream
    ↓
Next.js Frontend
```

---

## Package & Library Stack

### Framework & Runtime

```bash
npx create-next-app@latest growth-intelligence --typescript --tailwind --app --src-dir
```

| Package | Version | Purpose |
|---|---|---|
| `next` | 15.x | App Router framework |
| `react` | 19.x | UI runtime |
| `typescript` | 5.x | Type safety across streaming payloads |

### UI System

```bash
npx shadcn@latest init
```

Use **Slate** base color during shadcn init. Then add required components:

```bash
npx shadcn@latest add button card badge sheet skeleton tooltip
npx shadcn@latest add table tabs progress separator
npx shadcn@latest add scroll-area resizable
```

| Package | Purpose |
|---|---|
| `shadcn/ui` | Component primitives — Sheet (chat panel), Card, Badge, Skeleton |
| `tailwindcss` | v4 utility classes |
| `lucide-react` | Icon library — consistent with shadcn, no emojis |
| `tailwind-animate` | CSS keyframe supplements for hover/entrance states |

### Animation

```bash
npm install framer-motion
```

| Package | Purpose |
|---|---|
| `framer-motion` v11 | Slide-in chat panel, card entrances, artifact reveals, skeleton-to-content transitions |

### Data Visualization

```bash
npm install recharts @nivo/heatmap @nivo/treemap @nivo/core react-grid-layout
```

| Package | Purpose |
|---|---|
| `recharts` | Line charts (trends), bar charts (win/loss) — React-native, works with streaming state |
| `@nivo/heatmap` | Pricing & packaging competitor heat map |
| `@nivo/treemap` | Adjacent market threat visualization |
| `react-grid-layout` | Draggable, resizable dashboard card grid |

### State Management & Real-time

```bash
npm install zustand immer
```

| Package | Purpose |
|---|---|
| `zustand` | Global store — broadcasts incoming agent events to all subscribed dashboard cards |
| `immer` | Safe immutable state updates from streaming payloads |
| Native `EventSource` | SSE protocol — no extra package needed |

### Tables

```bash
npm install @tanstack/react-table
```

| Package | Purpose |
|---|---|
| `@tanstack/react-table` v8 | Virtualized, sortable, filterable tables for competitive data |

### Forms & Validation

```bash
npm install react-hook-form zod @hookform/resolvers
```

| Package | Purpose |
|---|---|
| `react-hook-form` | Chat input and query configuration forms |
| `zod` | Runtime schema validation for all user input AND incoming agent event payloads |

### Utilities

```bash
npm install date-fns clsx tailwind-merge nanoid dompurify
npm install -D @types/dompurify
```

| Package | Purpose |
|---|---|
| `date-fns` | Date formatting for trend charts |
| `clsx` + `tailwind-merge` | Included with shadcn; safe class merging |
| `nanoid` | Client-side message ID generation |
| `dompurify` | Sanitize any text content before rendering in chart labels or DOM |

---

## Shadcn Theme Configuration

In `src/app/globals.css`, override the default shadcn blue accent with a teal/cyan that fits a data intelligence product:

```css
@layer base {
  :root {
    --radius: 0.5rem;
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    /* Teal primary — intelligence/data feel */
    --primary: 172 80% 38%;
    --primary-foreground: 0 0% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 172 60% 92%;
    --accent-foreground: 172 80% 20%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 0 0% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 172 80% 38%;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --card: 222.2 84% 4.9%;
    --card-foreground: 210 40% 98%;
    --primary: 172 70% 50%;
    --primary-foreground: 222.2 47.4% 11.2%;
    --secondary: 217.2 32.6% 17.5%;
    --secondary-foreground: 210 40% 98%;
    --muted: 217.2 32.6% 17.5%;
    --muted-foreground: 215 20.2% 65.1%;
    --accent: 172 50% 15%;
    --accent-foreground: 172 70% 70%;
    --border: 217.2 32.6% 17.5%;
    --ring: 172 70% 50%;
  }
}
```

---

## Project File Structure

```
src/
├── app/
│   ├── layout.tsx                    ← root layout, fonts, providers
│   ├── page.tsx                      ← root page: dashboard + chat shell
│   ├── globals.css                   ← shadcn theme overrides
│   └── api/
│       ├── query/
│       │   └── route.ts              ← POST: receive user query, trigger backend agent run
│       └── stream/
│           └── route.ts              ← GET: SSE event stream proxy from backend
│
├── components/
│   ├── layout/
│   │   ├── RootShell.tsx             ← manages 2/3 + 1/3 split animation
│   │   └── AgentStatusBar.tsx        ← 8 pill indicators, idle/running/complete states
│   │
│   ├── dashboard/
│   │   ├── DashboardGrid.tsx         ← react-grid-layout wrapper
│   │   ├── ArtifactCard.tsx          ← base card with skeleton→content transition
│   │   └── cards/
│   │       ├── MarketTrendsCard.tsx          ← Agent 2 output
│   │       ├── CompetitiveLandscapeCard.tsx  ← Agent 3 output
│   │       ├── WinLossCard.tsx               ← Agent 4 output
│   │       ├── PricingPackagingCard.tsx      ← Agent 5 output
│   │       ├── PositioningCard.tsx           ← Agent 6 output
│   │       └── AdjacentMarketsCard.tsx       ← Agent 7 output
│   │
│   ├── chat/
│   │   ├── ChatPanel.tsx             ← shadcn Sheet, slide-in from right
│   │   ├── ChatMessage.tsx           ← individual message bubble
│   │   ├── ChatInput.tsx             ← react-hook-form input + send button
│   │   ├── ClarificationChips.tsx    ← follow-up suggestion badges
│   │   └── SourceTrail.tsx           ← expandable source list per message
│   │
│   └── ui/                           ← shadcn generated components (do not edit manually)
│
├── hooks/
│   ├── useAgentStream.ts             ← connects to SSE, dispatches to Zustand
│   ├── useDashboardLayout.ts         ← react-grid-layout state + persistence
│   └── useChatPanel.ts               ← panel open/close state + animation trigger
│
├── store/
│   └── index.ts                      ← Zustand store with immer middleware
│
├── types/
│   ├── agents.ts                     ← AgentEvent union types
│   ├── artifacts.ts                  ← per-domain payload types
│   └── chat.ts                       ← ChatMessage, SourceItem types
│
└── lib/
    ├── sanitize.ts                   ← DOMPurify wrapper for all rendered text
    ├── validate.ts                   ← Zod schemas for all event payloads
    └── utils.ts                      ← cn() helper from shadcn
```

---

## TypeScript Type Definitions

### `src/types/agents.ts`

```typescript
export type AgentId = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export type AgentStatus = 'idle' | 'running' | 'complete' | 'error';

export type Domain =
  | 'market_trends'
  | 'competitive_landscape'
  | 'win_loss'
  | 'pricing_packaging'
  | 'positioning'
  | 'adjacent_markets';

export type AgentEvent =
  | {
      type: 'agent_start';
      agentId: AgentId;
      label: string;
      statusMessage: string; // e.g. "Scanning 47 competitor pages..."
    }
  | {
      type: 'artifact_update';
      domain: Domain;
      payload: ArtifactPayload;
    }
  | {
      type: 'agent_complete';
      agentId: AgentId;
      confidence: number; // 0–1
    }
  | {
      type: 'compiler_output';
      summary: string;
      findings: Finding[];
    }
  | {
      type: 'stream_end';
    }
  | {
      type: 'error';
      agentId: AgentId;
      message: string; // NEVER expose raw backend errors — use generic messages
    };

export interface Finding {
  domain: Domain;
  headline: string;
  detail: string;
  confidence: number;
  sources: SourceItem[];
}

export interface SourceItem {
  url: string;
  title: string;
  retrievedAt: string; // ISO date string
  confidence: number;
}
```

### `src/types/artifacts.ts`

```typescript
export interface MarketTrendsPayload {
  trendLines: Array<{
    label: string;
    data: Array<{ date: string; value: number }>;
  }>;
  leadingIndicators: Array<{ label: string; direction: 'up' | 'down' | 'flat'; magnitude: number }>;
}

export interface CompetitivePayload {
  competitors: Array<{
    name: string;
    features: Record<string, boolean | string>;
    lastUpdated: string;
  }>;
  featureColumns: string[];
}

export interface WinLossPayload {
  reasons: Array<{ reason: string; wins: number; losses: number }>;
  buyerSentiment: Array<{ label: string; score: number }>;
}

export interface PricingPayload {
  matrix: Array<{
    competitor: string;
    tiers: Array<{ name: string; price: number | null; willingnessScore: number }>;
  }>;
}

export interface PositioningPayload {
  gaps: Array<{ dimension: string; ourScore: number; marketExpectation: number; delta: number }>;
  messagingSuggestions: string[];
}

export interface AdjacentMarketsPayload {
  threats: Array<{
    category: string;
    source: string;
    threatLevel: 'low' | 'medium' | 'high';
    size: number; // for treemap
  }>;
}

export type ArtifactPayload =
  | MarketTrendsPayload
  | CompetitivePayload
  | WinLossPayload
  | PricingPayload
  | PositioningPayload
  | AdjacentMarketsPayload;
```

---

## Zustand Store

### `src/store/index.ts`

```typescript
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { AgentId, AgentStatus, Domain, Finding, SourceItem } from '@/types/agents';
import type { ArtifactPayload } from '@/types/artifacts';

interface AgentState {
  status: AgentStatus;
  statusMessage: string;
  confidence: number;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  clarificationChips?: string[];
  timestamp: number;
}

interface AppState {
  // Agent pipeline state
  agents: Record<AgentId, AgentState>;
  artifacts: Partial<Record<Domain, ArtifactPayload>>;
  compilerFindings: Finding[];

  // Chat state
  isChatOpen: boolean;
  chatMessages: ChatMessage[];
  isStreaming: boolean;

  // Actions
  setAgentStatus: (id: AgentId, status: AgentStatus, message?: string) => void;
  setAgentConfidence: (id: AgentId, confidence: number) => void;
  updateArtifact: (domain: Domain, payload: ArtifactPayload) => void;
  setCompilerFindings: (findings: Finding[]) => void;
  toggleChat: () => void;
  addMessage: (message: ChatMessage) => void;
  resetPipeline: () => void;
  setStreaming: (val: boolean) => void;
}

const initialAgentState: AgentState = { status: 'idle', statusMessage: '', confidence: 0 };

export const useAppStore = create<AppState>()(
  immer((set) => ({
    agents: {
      1: { ...initialAgentState },
      2: { ...initialAgentState },
      3: { ...initialAgentState },
      4: { ...initialAgentState },
      5: { ...initialAgentState },
      6: { ...initialAgentState },
      7: { ...initialAgentState },
      8: { ...initialAgentState },
    },
    artifacts: {},
    compilerFindings: [],
    isChatOpen: false,
    chatMessages: [],
    isStreaming: false,

    setAgentStatus: (id, status, message = '') =>
      set((state) => {
        state.agents[id].status = status;
        state.agents[id].statusMessage = message;
      }),

    setAgentConfidence: (id, confidence) =>
      set((state) => {
        state.agents[id].confidence = confidence;
      }),

    updateArtifact: (domain, payload) =>
      set((state) => {
        state.artifacts[domain] = payload;
      }),

    setCompilerFindings: (findings) =>
      set((state) => {
        state.compilerFindings = findings;
      }),

    toggleChat: () =>
      set((state) => {
        state.isChatOpen = !state.isChatOpen;
      }),

    addMessage: (message) =>
      set((state) => {
        state.chatMessages.push(message);
      }),

    resetPipeline: () =>
      set((state) => {
        state.artifacts = {};
        state.compilerFindings = [];
        ([1, 2, 3, 4, 5, 6, 7, 8] as AgentId[]).forEach((id) => {
          state.agents[id] = { ...initialAgentState };
        });
      }),

    setStreaming: (val) =>
      set((state) => {
        state.isStreaming = val;
      }),
  }))
);
```

---

## SSE Hook

### `src/hooks/useAgentStream.ts`

```typescript
import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store';
import { validateAgentEvent } from '@/lib/validate';
import type { AgentEvent } from '@/types/agents';

export function useAgentStream(queryId: string | null) {
  const store = useAppStore();
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!queryId) return;

    // Close any existing connection
    esRef.current?.close();

    store.resetPipeline();
    store.setStreaming(true);

    const es = new EventSource(`/api/stream?queryId=${encodeURIComponent(queryId)}`);
    esRef.current = es;

    es.onmessage = (event) => {
      let parsed: AgentEvent;
      try {
        const raw = JSON.parse(event.data);
        // Validate shape before trusting the payload
        parsed = validateAgentEvent(raw);
      } catch {
        // Malformed event — silently discard, do not crash UI
        console.warn('Discarded malformed agent event');
        return;
      }

      switch (parsed.type) {
        case 'agent_start':
          store.setAgentStatus(parsed.agentId, 'running', parsed.statusMessage);
          break;
        case 'artifact_update':
          store.updateArtifact(parsed.domain, parsed.payload);
          break;
        case 'agent_complete':
          store.setAgentStatus(parsed.agentId, 'complete');
          store.setAgentConfidence(parsed.agentId, parsed.confidence);
          break;
        case 'compiler_output':
          store.setCompilerFindings(parsed.findings);
          break;
        case 'stream_end':
          store.setStreaming(false);
          es.close();
          break;
        case 'error':
          // Generic UI error — never expose raw backend error message
          store.setAgentStatus(parsed.agentId, 'error', 'Agent failed to retrieve data');
          break;
      }
    };

    es.onerror = () => {
      store.setStreaming(false);
      es.close();
    };

    return () => {
      es.close();
      store.setStreaming(false);
    };
  }, [queryId]);
}
```

---

## Layout: Split-Screen Shell

### `src/components/layout/RootShell.tsx`

```tsx
'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store';
import { DashboardGrid } from '@/components/dashboard/DashboardGrid';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ChatFloatingButton } from '@/components/chat/ChatFloatingButton';
import { AgentStatusBar } from '@/components/layout/AgentStatusBar';

export function RootShell() {
  const isChatOpen = useAppStore((s) => s.isChatOpen);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Dashboard region — animates width on chat open/close */}
      <motion.div
        className="flex flex-col h-full overflow-hidden"
        animate={{ width: isChatOpen ? '66.666%' : '100%' }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      >
        <AgentStatusBar />
        <div className="flex-1 overflow-auto p-4">
          <DashboardGrid />
        </div>
      </motion.div>

      {/* Chat panel — slides in from the right */}
      <AnimatePresence>
        {isChatOpen && (
          <motion.div
            className="h-full border-l border-border bg-background"
            style={{ width: '33.333%' }}
            initial={{ x: '100%', opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            <ChatPanel />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating chat button — bottom right */}
      <ChatFloatingButton />
    </div>
  );
}
```

---

## Dashboard Cards: Artifact-to-Chart Mapping

### Card Skeleton → Live Content Pattern

Every domain card follows this pattern:

```tsx
'use client';

import { useAppStore } from '@/store';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { motion, AnimatePresence } from 'framer-motion';

export function MarketTrendsCard() {
  const artifact = useAppStore((s) => s.artifacts.market_trends);
  const agentState = useAppStore((s) => s.agents[2]);

  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">Market & Trends</CardTitle>
        {agentState.status === 'complete' && (
          <Badge variant="outline" className="text-xs">
            {Math.round(agentState.confidence * 100)}% confidence
          </Badge>
        )}
      </CardHeader>
      <CardContent>
        <AnimatePresence mode="wait">
          {!artifact ? (
            <motion.div
              key="skeleton"
              initial={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-2"
            >
              {agentState.statusMessage && (
                <p className="text-xs text-muted-foreground animate-pulse">
                  {agentState.statusMessage}
                </p>
              )}
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-32 w-full" />
            </motion.div>
          ) : (
            <motion.div
              key="content"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
            >
              {/* Recharts LineChart with artifact.trendLines data */}
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
```

### Chart Assignments per Card

| Card | Agent | Chart Type | Library | Key Data Shape |
|---|---|---|---|---|
| `MarketTrendsCard` | 2 | `LineChart` | recharts | `trendLines[].data[]` |
| `CompetitiveLandscapeCard` | 3 | Feature matrix table | TanStack Table | `competitors[].features{}` |
| `WinLossCard` | 4 | `BarChart` grouped + sentiment badges | recharts | `reasons[].wins/losses` |
| `PricingPackagingCard` | 5 | Heat map | `@nivo/heatmap` | `matrix[].tiers[].willingnessScore` |
| `PositioningCard` | 6 | Radar / gap scorecard | recharts `RadarChart` | `gaps[].ourScore/marketExpectation` |
| `AdjacentMarketsCard` | 7 | Treemap | `@nivo/treemap` | `threats[].size/threatLevel` |

---

## Agent Status Bar

### `src/components/layout/AgentStatusBar.tsx`

```tsx
'use client';

import { useAppStore } from '@/store';
import { Badge } from '@/components/ui/badge';
import { motion } from 'framer-motion';
import { CheckCircle, Circle, Loader, AlertCircle } from 'lucide-react';

const AGENT_LABELS: Record<number, string> = {
  1: 'Fetcher',
  2: 'Market',
  3: 'Competitive',
  4: 'Win/Loss',
  5: 'Pricing',
  6: 'Positioning',
  7: 'Adjacent',
  8: 'Compiler',
};

const STATUS_ICON = {
  idle: Circle,
  running: Loader,
  complete: CheckCircle,
  error: AlertCircle,
};

const STATUS_CLASS = {
  idle: 'text-muted-foreground',
  running: 'text-primary animate-spin',
  complete: 'text-green-500',
  error: 'text-destructive',
};

export function AgentStatusBar() {
  const agents = useAppStore((s) => s.agents);

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/30 overflow-x-auto">
      <span className="text-xs text-muted-foreground font-medium shrink-0 mr-2">Agents</span>
      {([1, 2, 3, 4, 5, 6, 7, 8] as const).map((id) => {
        const agent = agents[id];
        const Icon = STATUS_ICON[agent.status];
        return (
          <motion.div
            key={id}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-1 shrink-0"
          >
            <Icon className={`w-3 h-3 ${STATUS_CLASS[agent.status]}`} />
            <span className="text-xs text-muted-foreground">{AGENT_LABELS[id]}</span>
            {agent.status === 'complete' && agent.confidence > 0 && (
              <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">
                {Math.round(agent.confidence * 100)}%
              </Badge>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
```

---

## Chat Panel Components

### `src/components/chat/ChatPanel.tsx`

```tsx
'use client';

import { useRef, useEffect } from 'react';
import { useAppStore } from '@/store';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ChatPanel() {
  const { chatMessages, toggleChat } = useAppStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <span className="text-sm font-medium">Growth Intelligence</span>
        <Button variant="ghost" size="icon" onClick={toggleChat}>
          <X className="w-4 h-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 px-4">
        <div className="space-y-4 py-4">
          {chatMessages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="border-t border-border p-4">
        <ChatInput />
      </div>
    </div>
  );
}
```

### `src/components/chat/SourceTrail.tsx`

```tsx
'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { SourceItem } from '@/types/agents';

interface SourceTrailProps {
  sources: SourceItem[];
}

export function SourceTrail({ sources }: SourceTrailProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!sources.length) return null;

  return (
    <div className="mt-2">
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs text-muted-foreground"
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? <ChevronUp className="w-3 h-3 mr-1" /> : <ChevronDown className="w-3 h-3 mr-1" />}
        {sources.length} source{sources.length !== 1 ? 's' : ''}
      </Button>

      {isOpen && (
        <div className="mt-1 space-y-1 border-l-2 border-border pl-3">
          {sources.map((source, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline truncate block"
                >
                  {source.title}
                  <ExternalLink className="inline w-2.5 h-2.5 ml-1 opacity-60" />
                </a>
                <span className="text-[10px] text-muted-foreground">
                  {Math.round(source.confidence * 100)}% confidence
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## API Routes (Next.js)

### `src/app/api/query/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

const QuerySchema = z.object({
  query: z.string().min(1).max(500).trim(),
  sessionId: z.string().uuid().optional(),
});

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const parsed = QuerySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid query' }, { status: 400 });
  }

  // Forward to backend — API keys are on the server, never the client
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 503 });
  }

  try {
    const response = await fetch(`${backendUrl}/api/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.BACKEND_API_KEY}`,
      },
      body: JSON.stringify(parsed.data),
    });

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    // Never expose internal error details to the client
    return NextResponse.json({ error: 'Failed to initiate query' }, { status: 502 });
  }
}
```

### `src/app/api/stream/route.ts`

```typescript
import { NextRequest } from 'next/server';

export async function GET(request: NextRequest) {
  const queryId = request.nextUrl.searchParams.get('queryId');

  if (!queryId || !/^[a-zA-Z0-9_-]{1,64}$/.test(queryId)) {
    return new Response('Invalid queryId', { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    return new Response('Service unavailable', { status: 503 });
  }

  // Proxy the SSE stream from backend to client
  // API keys never leave the server
  const upstreamResponse = await fetch(
    `${backendUrl}/api/stream?queryId=${encodeURIComponent(queryId)}`,
    {
      headers: {
        Authorization: `Bearer ${process.env.BACKEND_API_KEY}`,
        Accept: 'text/event-stream',
      },
    }
  );

  if (!upstreamResponse.ok || !upstreamResponse.body) {
    return new Response('Stream unavailable', { status: 502 });
  }

  return new Response(upstreamResponse.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}
```

---

## Input Validation

### `src/lib/validate.ts`

```typescript
import { z } from 'zod';
import type { AgentEvent } from '@/types/agents';

const SourceItemSchema = z.object({
  url: z.string().url(),
  title: z.string().max(200),
  retrievedAt: z.string(),
  confidence: z.number().min(0).max(1),
});

const FindingSchema = z.object({
  domain: z.enum(['market_trends', 'competitive_landscape', 'win_loss', 'pricing_packaging', 'positioning', 'adjacent_markets']),
  headline: z.string().max(300),
  detail: z.string().max(2000),
  confidence: z.number().min(0).max(1),
  sources: z.array(SourceItemSchema),
});

const AgentEventSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('agent_start'), agentId: z.number().int().min(1).max(8), label: z.string(), statusMessage: z.string() }),
  z.object({ type: z.literal('artifact_update'), domain: z.string(), payload: z.record(z.unknown()) }),
  z.object({ type: z.literal('agent_complete'), agentId: z.number().int().min(1).max(8), confidence: z.number().min(0).max(1) }),
  z.object({ type: z.literal('compiler_output'), summary: z.string(), findings: z.array(FindingSchema) }),
  z.object({ type: z.literal('stream_end') }),
  z.object({ type: z.literal('error'), agentId: z.number().int().min(1).max(8), message: z.string() }),
]);

export function validateAgentEvent(raw: unknown): AgentEvent {
  return AgentEventSchema.parse(raw) as AgentEvent;
}
```

### `src/lib/sanitize.ts`

```typescript
import DOMPurify from 'dompurify';

/**
 * Sanitize any string before it touches the DOM.
 * Use this on ALL text sourced from agent outputs before
 * passing to chart labels, table cells, or rendered text.
 */
export function sanitize(input: string): string {
  if (typeof window === 'undefined') {
    // Server-side: strip all tags with a simple regex fallback
    return input.replace(/<[^>]*>/g, '').slice(0, 1000);
  }
  return DOMPurify.sanitize(input, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] });
}
```

---

## `next.config.ts`

```typescript
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'", // unsafe-eval needed for Next.js dev
              "style-src 'self' 'unsafe-inline'",
              `connect-src 'self' ${process.env.NEXT_PUBLIC_BACKEND_ORIGIN ?? ''}`,
              "img-src 'self' data: https:",
              "font-src 'self'",
              "frame-ancestors 'none'",
            ].join('; '),
          },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
```

---

## `.env.local` (never commit this file)

```bash
# Backend service
BACKEND_URL=http://localhost:8000
BACKEND_API_KEY=your_secret_key_here

# Expose only the origin (no keys) to the client for CSP
NEXT_PUBLIC_BACKEND_ORIGIN=http://localhost:8000

# Never add SERPAPI_KEY, FIRECRAWL_KEY, or any third-party keys here
# Those live exclusively on the backend
```

---

## Build Phases & Time Allocation

| Phase | Duration | Deliverable |
|---|---|---|
| **Phase 1 — Scaffold & Layout** | Hours 1–2 | Next.js setup, split-screen shell working, chat panel slide-in, Zustand store |
| **Phase 2 — Streaming & State** | Hours 2–3 | `useAgentStream` hook, event dispatch, agent status bar with live indicators |
| **Phase 3 — Dashboard Cards** | Hours 3–6 | All 6 domain cards with skeleton → live chart transitions, react-grid-layout |
| **Phase 4 — Chat Interface** | Hours 5–6 | Message list, input, clarification chips, source trail component |
| **Phase 5 — Polish** | Final 30 min | Error boundaries, loading messages, demo run-through |

> **Critical path note:** Complete Phase 2 before touching any chart code. The streaming/state sync is the highest-risk item — everything else depends on it working correctly.

---

## Demo Engineering Checklist

The judges assess **process depth**, not just output. Engineer these moments:

- [ ] Agent status bar shows 6 agents spinning in parallel — this is itself a judging signal
- [ ] Each card skeleton shows a live status ticker (e.g. "Reading 23 reviews on G2…") sourced from `agent_start.statusMessage`
- [ ] Cards animate out and back in (fade/blur, not hard-cut) when a new chat query resets the pipeline
- [ ] `SourceTrail` expand/collapse is prominently visible per message — this proves "live signal only"
- [ ] Confidence badges visible on each card and agent pill
- [ ] Drag-to-rearrange dashboard cards works live in the demo
- [ ] System generalises to a second product (beyond Vector Agents) — have a second query ready

---

## Security Checklist

- [ ] No third-party API keys in any `NEXT_PUBLIC_` environment variable
- [ ] All user input validated with Zod before reaching the backend
- [ ] All agent output validated with Zod before touching Zustand state
- [ ] All rendered text from agent payloads passes through `sanitize()` from `lib/sanitize.ts`
- [ ] Chart labels populated with `sanitize(text)` — not raw payload strings
- [ ] API routes return generic error messages — no stack traces, no internal paths
- [ ] `Content-Security-Policy` header set in `next.config.ts`
- [ ] `.env.local` is in `.gitignore` — confirm before pushing to the hackathon repo
- [ ] SSE endpoint validates `queryId` format before proxying to backend
- [ ] CORS on the backend locked to the Next.js frontend origin only