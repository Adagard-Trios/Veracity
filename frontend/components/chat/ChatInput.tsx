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
  const [subgraph, setSubgraph] = useState("All");
  const addMessage = useAppStore((s) => s.addMessage);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const setStreaming = useAppStore((s) => s.setStreaming);
  
  // Attach SSE hook (this now listens globally to the background loop)
  useAgentStream(null);

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

    try {
      setStreaming(true);
      const response = await fetch('http://127.0.0.1:8000/api/rag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: values.query, subgraph_context: subgraph }),
      });
      
      const responseData = await response.json();
      
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: responseData.answer || "No specific answer was returned.",
        timestamp: Date.now(),
      });
    } catch (e) {
      console.error(e);
      addMessage({
        id: nanoid(),
        role: 'assistant',
        content: "I'm sorry, I couldn't reach the RAG backend to process your query right now.",
        timestamp: Date.now(),
      });
    } finally {
      setStreaming(false);
    }

    form.reset();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground whitespace-nowrap">Brain Context:</span>
        <select 
          value={subgraph}
          onChange={(e) => setSubgraph(e.target.value)}
          className="h-7 text-xs rounded-md border border-input bg-transparent px-2 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isStreaming}
        >
          <option value="All">All (General Data)</option>
          <option value="Pricing">Pricing</option>
          <option value="Competitor">Competitor</option>
          <option value="Adjacent Market">Adjacent Market</option>
          <option value="Market Trend">Market Trend</option>
          <option value="User Voice">User Voice</option>
          <option value="Win-Loss">Win-Loss</option>
        </select>
      </div>
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
    </div>
  );
}
