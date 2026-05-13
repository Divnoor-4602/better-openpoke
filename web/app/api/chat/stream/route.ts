export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
  const url = `${serverBase.replace(/\/$/, '')}/api/chat/stream`;

  try {
    const upstream = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: await req.text(),
      cache: 'no-store',
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'text/event-stream',
        'Cache-Control': upstream.headers.get('cache-control') || 'no-cache',
        'x-vercel-ai-ui-message-stream':
          upstream.headers.get('x-vercel-ai-ui-message-stream') || 'v1',
      },
    });
  } catch (error: any) {
    const message = error?.message || 'Failed to reach Python server';
    return new Response(message, { status: 502 });
  }
}
