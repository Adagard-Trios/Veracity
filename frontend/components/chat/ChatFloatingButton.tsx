'use client';

import { useAppStore } from '@/store';
import { Button } from '@/components/ui/button';
import { MessageSquare } from 'lucide-react';

export function ChatFloatingButton() {
  const { isChatOpen, toggleChat } = useAppStore();

  if (isChatOpen) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <Button
        size="icon"
        className="h-14 w-14 rounded-full shadow-lg"
        onClick={toggleChat}
      >
        <MessageSquare className="h-6 w-6" />
      </Button>
    </div>
  );
}
