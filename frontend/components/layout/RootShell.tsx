'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useAppStore } from '@/store';
import { DashboardGrid } from '@/components/dashboard/DashboardGrid';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { ChatFloatingButton } from '@/components/chat/ChatFloatingButton';
import { AgentStatusBar } from '@/components/layout/AgentStatusBar';

export function RootShell() {
  const isChatOpen = useAppStore((s) => s.isChatOpen);
  const loadMockData = useAppStore((s) => s.loadMockData);

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

      {/* Dev only: Load Mock Data Button */}
      {process.env.NODE_ENV === 'development' && (
        <button
          onClick={loadMockData}
          className="fixed bottom-4 left-4 z-50 rounded-md bg-primary px-4 py-2 text-primary-foreground shadow-md hover:bg-primary/90"
        >
          Load Mock Data
        </button>
      )}
    </div>
  );
}
