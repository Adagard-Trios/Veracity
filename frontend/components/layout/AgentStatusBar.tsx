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
