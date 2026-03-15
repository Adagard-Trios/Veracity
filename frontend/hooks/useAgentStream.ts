import { useEffect, useRef } from 'react';
import { useAppStore } from '@/store';
import { validateAgentEvent } from '@/lib/validate';
import type { AgentEvent } from '@/types/agents';

export function useAgentStream(queryId: string | null) {
  const store = useAppStore();
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Determine if we should connect to the stream.
    // In our new architecture, the stream is global for the background loop.
    // So we can connect unconditionally when the hook mounts.
    
    // Close any existing connection
    esRef.current?.close();

    store.resetPipeline();
    store.setStreaming(true);

    const es = new EventSource(`http://127.0.0.1:8000/api/stream`);
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryId]);
}
