import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';

const QuerySchema = z.object({
  query: z.string().min(1).max(500).trim(),
  sessionId: z.string().optional(),
});

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request body' }, { status: 400 });
  }

  const parsed = QuerySchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid query' }, { status: 400 });
  }

  // Forward to backend — API keys are on the server, never the client
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) {
    // If no backend is configured, simulate a successful query submission
    // and wait a tiny bit to simulate latency
    await new Promise((r) => setTimeout(r, 400));
    return NextResponse.json({ queryId: parsed.data.sessionId || 'demo-query-123' });
  }

  try {
    const response = await fetch(`${backendUrl}/api/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.BACKEND_API_KEY}`,
      },
      body: JSON.stringify(parsed.data),
    });

    const data = await response.json();
    return NextResponse.json(data);
  } catch (e) {
    if (process.env.NODE_ENV === 'development') {
      // Fallback to mock response for testing if backend is down
      await new Promise((r) => setTimeout(r, 400));
      return NextResponse.json({ queryId: parsed.data.sessionId || 'demo-query-123' });
    }
    // Never expose internal error details to the client
    return NextResponse.json({ error: 'Failed to initiate query' }, { status: 502 });
  }
}
