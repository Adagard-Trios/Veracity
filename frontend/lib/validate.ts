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

export function validateAgentEvent(raw: unknown): AgentEvent {
  return raw as AgentEvent;
}
