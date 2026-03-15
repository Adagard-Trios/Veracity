'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store';
import { nanoid } from 'nanoid';
import { useAgentStream } from '@/hooks/useAgentStream';

const formSchema = z.object({
  query: z.string().min(1),
});

export function ChatInput() {
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null);
  const addMessage = useAppStore((s) => s.addMessage);
  const isStreaming = useAppStore((s) => s.isStreaming);
  
  // Attach SSE hook
  useAgentStream(activeQueryId);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: { query: '' },
  });

  async function onSubmit(values: z.infer<typeof formSchema>) {
    if (isStreaming) return;

    // Add user message
    addMessage({
      id: nanoid(),
      role: 'user',
      content: values.query,
      timestamp: Date.now(),
    });

    const queryId = nanoid();
    
    // Fire to backend proxy
    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: values.query, sessionId: queryId }),
      });
      
      const responseData = await response.json();
      
      // Add simulated AI acknowledgement
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: `I'm analyzing the market data for your query: "${values.query}". I've dispatched 6 sub-agents to scan competitor landscapes, review win/loss data, and compile pricing structures. I'll update the dashboard as soon as they report back.`,
        timestamp: Date.now(),
      });

      // Set active query ID to trigger SSE hook
      setActiveQueryId(responseData.queryId || queryId);
    } catch (e) {
      console.error(e);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: "I'm sorry, I couldn't reach the backend to process your query right now.",
        timestamp: Date.now(),
      });
    }

    form.reset();
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="flex items-center gap-2">
      <input
        {...form.register('query')}
        placeholder="Ask the growth intelligence..."
        className="flex-1 h-10 px-3 rounded-md border border-input bg-transparent text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        disabled={isStreaming}
        autoComplete="off"
      />
      <Button type="submit" size="icon" disabled={isStreaming || !form.watch('query')}>
        <Send className="w-4 h-4" />
      </Button>
    </form>
  );
}
