'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Play, Square } from 'lucide-react';
import { useAppStore } from '@/store';

const formSchema = z.object({
  brand: z.string().min(1, 'Brand is required'),
  category: z.string().min(1, 'Category is required'),
  query: z.string().min(1, 'Query is required'),
  urls: z.string().min(1, 'URLs are required (comma separated)'),
  competitors: z.string().optional(),
});

export function AgentControlPanel() {
  const [isRunning, setIsRunning] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      brand: 'Stripe',
      category: 'Payment Processing',
      query: 'How do customers compare us vs Adyen for global expansion?',
      urls: 'https://stripe.com, https://adyen.com',
      competitors: 'Adyen, Square',
    },
  });

  const startLoop = async (values: z.infer<typeof formSchema>) => {
    setErrorMsg('');
    try {
      const payload = {
        brand: values.brand,
        category: values.category,
        query: values.query,
        urls: values.urls.split(',').map(s => s.trim()),
        competitors: values.competitors ? values.competitors.split(',').map(s => s.trim()) : [],
        pdf_paths: [],
        txt_paths: []
      };

      const res = await fetch('http://127.0.0.1:8000/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) throw new Error('Failed to start loop');
      setIsRunning(true);
    } catch (e: any) {
      setErrorMsg(e.message);
    }
  };

  const stopLoop = async () => {
    try {
      await fetch('http://127.0.0.1:8000/api/stop', { method: 'POST' });
      setIsRunning(false);
    } catch (e: any) {
      setErrorMsg(e.message);
    }
  };

  return (
    <div className="bg-card text-card-foreground border border-border/50 rounded-xl p-4 shadow-sm mb-4">
      <div className="flex justify-between items-center mb-4">
        <h3 className="font-semibold text-lg">Growth Intelligence Engine</h3>
        <div className="flex gap-2">
          {!isRunning ? (
            <Button onClick={form.handleSubmit(startLoop)} size="sm" className="bg-primary text-primary-foreground">
              <Play className="w-4 h-4 mr-2" /> Start Analysis Loop
            </Button>
          ) : (
            <Button onClick={stopLoop} size="sm" variant="destructive">
              <Square className="w-4 h-4 mr-2" /> Stop Loop
            </Button>
          )}
        </div>
      </div>
      
      {!isRunning && (
        <form className="grid grid-cols-2 gap-4 text-sm" onSubmit={form.handleSubmit(startLoop)}>
          <div className="space-y-1">
            <label className="text-muted-foreground">Brand</label>
            <input {...form.register('brand')} className="w-full bg-background border border-input rounded-md px-3 py-1.5" />
          </div>
          <div className="space-y-1">
            <label className="text-muted-foreground">Category</label>
            <input {...form.register('category')} className="w-full bg-background border border-input rounded-md px-3 py-1.5" />
          </div>
          <div className="space-y-1 col-span-2">
            <label className="text-muted-foreground">Research Query</label>
            <input {...form.register('query')} className="w-full bg-background border border-input rounded-md px-3 py-1.5" />
          </div>
          <div className="space-y-1">
            <label className="text-muted-foreground">Target URLs (comma separated)</label>
            <input {...form.register('urls')} className="w-full bg-background border border-input rounded-md px-3 py-1.5" />
          </div>
          <div className="space-y-1">
            <label className="text-muted-foreground">Competitors (comma separated)</label>
            <input {...form.register('competitors')} className="w-full bg-background border border-input rounded-md px-3 py-1.5" />
          </div>
          {errorMsg && <p className="text-destructive col-span-2">{errorMsg}</p>}
        </form>
      )}
      {isRunning && (
        <div className="p-4 bg-muted/50 rounded-lg text-sm text-muted-foreground flex items-center justify-center animate-pulse">
          Agent swarm is actively running in the background...
        </div>
      )}
    </div>
  );
}
