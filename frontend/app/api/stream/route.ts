import { NextRequest } from 'next/server';
import { mockArtifacts } from '@/lib/mockData';

function getMockStream() {
  const stream = new ReadableStream({
    async start(controller) {
      const send = (data: any) => {
        controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      // 1. Start pipeline
      send({ type: 'agent_start', agentId: 1, label: 'Intake', statusMessage: 'Parsing query...' });
      await new Promise((r) => setTimeout(r, 600));
      send({ type: 'agent_complete', agentId: 1, confidence: 1 });

      // Start worker agents
      const workers = [
        { id: 2, domain: 'market_trends', label: 'Market & Trends' },
        { id: 3, domain: 'competitive_landscape', label: 'Competitive Landscape' },
        { id: 4, domain: 'win_loss', label: 'Win/Loss Analysis' },
        { id: 5, domain: 'pricing_packaging', label: 'Pricing & Packaging' },
        { id: 6, domain: 'positioning', label: 'Positioning' },
        { id: 7, domain: 'adjacent_markets', label: 'Adjacent Markets' },
      ];

      for (const worker of workers) {
        send({ type: 'agent_start', agentId: worker.id, label: worker.label, statusMessage: `Gathering ${worker.label.toLowerCase()}...` });
      }

      // Stagger artifact updates
      for (const [index, worker] of workers.entries()) {
        await new Promise((r) => setTimeout(r, 800 + (index * 400))); // staggered delays
        send({ type: 'artifact_update', domain: worker.domain, payload: mockArtifacts[worker.domain as keyof typeof mockArtifacts] });
        send({ type: 'agent_complete', agentId: worker.id, confidence: 0.85 + (Math.random() * 0.1) });
      }

      // 3. Compiler Agent
      send({ type: 'agent_start', agentId: 8, label: 'Compiler', statusMessage: 'Synthesizing report...' });
      await new Promise((r) => setTimeout(r, 1000));
      send({
        type: 'compiler_output',
        summary: "Based on the mock data, we are well positioned in AI features but underperforming on price expectations at the enterprise level.",
        findings: []
      });
      send({ type: 'agent_complete', agentId: 8, confidence: 0.95 });

      // 4. End Stream
      await new Promise((r) => setTimeout(r, 500));
      send({ type: 'stream_end' });
      controller.close();
    }
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

export async function GET(request: NextRequest) {
  const queryId = request.nextUrl.searchParams.get('queryId');

  if (!queryId || !/^[a-zA-Z0-9_-]{1,64}$/.test(queryId)) {
    return new Response('Invalid queryId', { status: 400 });
  }

  const backendUrl = process.env.BACKEND_URL;
  
  // If no backend is configured, return a mock SSE stream for development/testing
  if (!backendUrl) {
    return getMockStream();
  }

  // Proxy the SSE stream from backend to client
  // API keys never leave the server
  try {
    const upstreamResponse = await fetch(
      `${backendUrl}/api/stream?queryId=${encodeURIComponent(queryId)}`,
      {
        headers: {
          Authorization: `Bearer ${process.env.BACKEND_API_KEY}`,
          Accept: 'text/event-stream',
        },
        // Ensure we don't hold the connection Open infinitely without bytes flowing
        // depending on node fetch implementation
      }
    );

    if (!upstreamResponse.ok || !upstreamResponse.body) {
      if (process.env.NODE_ENV === 'development') return getMockStream();
      return new Response('Stream unavailable', { status: 502 });
    }

    return new Response(upstreamResponse.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    // If fetch failed (e.g. backend isn't running), simulate mock data stream in dev environment!
    if (process.env.NODE_ENV === 'development') return getMockStream();
    return new Response('Service unavailable', { status: 503 });
  }
}
