'use client';

import { useEffect, useState } from 'react';
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
  const [loopStatus, setLoopStatus] = useState<{is_running: boolean, current_target: string | null}>({
    is_running: false,
    current_target: null
  });

  // Poll overall backend status
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/status');
        if (res.ok) {
          const data = await res.json();
          setLoopStatus({
            is_running: data.is_running,
            current_target: data.current_target
          });
        }
      } catch (e) {
        // Handle silently
      }
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/30 overflow-x-auto">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground font-medium shrink-0 mr-2">Agents</span>
        {([1, 2, 3, 4, 5, 6, 7, 8] as const).map((id) => {
          const agent = agents[id];
          const Icon = STATUS_ICON[agent.status] || Circle;
          const agentLabel = AGENT_LABELS[id] || `Agent ${id}`;
          return (
            <motion.div
              key={id}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-1 shrink-0 px-2"
            >
              <Icon className={`w-3 h-3 ${STATUS_CLASS[agent.status] || ''}`} />
              <span className="text-xs text-muted-foreground">{agentLabel}</span>
              {agent.status === 'complete' && agent.confidence > 0 && (
                <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">
                  {Math.round(agent.confidence * 100)}%
                </Badge>
              )}
            </motion.div>
          );
        })}
      </div>
      
      {/* Global Loop Status */}
      <div className="flex flex-col items-end shrink-0 ml-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Engine Status:</span>
          {loopStatus.is_running ? (
            <Badge className="bg-green-500/20 text-green-600 border border-green-500/30 flex items-center gap-1">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              Active ({loopStatus.current_target})
            </Badge>
          ) : (
             <Badge variant="outline" className="text-muted-foreground">Standby</Badge>
          )}
        </div>
      </div>
    </div>
  );
}
