export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type Params = {
  params: {
    requestId: string;
  };
};

export async function GET(req: Request, { params }: Params) {
  const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
  const url = new URL(
    `${serverBase.replace(/\/$/, '')}/api/execution/runs/${encodeURIComponent(params.requestId)}/stream`,
  );
  const afterId = new URL(req.url).searchParams.get('afterId');
  if (afterId) url.searchParams.set('afterId', afterId);

  try {
    const upstream = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
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
