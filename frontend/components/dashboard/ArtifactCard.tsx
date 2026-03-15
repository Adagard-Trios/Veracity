'use client';

import { useAppStore } from '@/store';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { motion, AnimatePresence } from 'framer-motion';
import type { AgentId, Domain } from '@/types/agents';

interface ArtifactCardProps {
  title: string;
  agentId: AgentId;
  domain: Domain;
  children: React.ReactNode;
}

export function ArtifactCard({ title, agentId, domain, children }: ArtifactCardProps) {
  const artifact = useAppStore((s) => s.artifacts[domain]);
  const agentState = useAppStore((s) => s.agents[agentId]);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {agentState.status === 'complete' && (
          <Badge variant="outline" className="text-xs">
            {Math.round(agentState.confidence * 100)}% confidence
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex-1 min-h-0 relative">
        <ScrollArea className="h-full w-full pr-3">
          <AnimatePresence mode="wait">
            {!artifact ? (
              <motion.div
                key="skeleton"
                initial={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-2"
              >
                {agentState.statusMessage && (
                  <p className="text-xs text-muted-foreground animate-pulse mb-4 h-8 overflow-hidden">
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
                className="h-full"
              >
                {children}
              </motion.div>
            )}
          </AnimatePresence>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
