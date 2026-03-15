import type { ArtifactPayload } from './artifacts';

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
