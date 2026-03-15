import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { AgentId, AgentStatus, Domain, Finding, SourceItem } from '@/types/agents';
import type { ArtifactPayload } from '@/types/artifacts';
import { mockArtifacts } from '@/lib/mockData';

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
  loadMockData: () => void;
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

    loadMockData: () =>
      set((state) => {
        state.artifacts = mockArtifacts as any;
        ([1, 2, 3, 4, 5, 6, 7, 8] as AgentId[]).forEach((id) => {
          state.agents[id] = { status: 'complete', statusMessage: 'Mock data loaded', confidence: 0.95 };
        });
      }),
  }))
);
