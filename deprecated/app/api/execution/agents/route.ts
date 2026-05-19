const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
const agentsPath = `${serverBase.replace(/\/$/, '')}/api/execution/agents`;

export async function GET() {
  try {
    const res = await fetch(agentsPath, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });

    const bodyText = await res.text();
    return new Response(bodyText || '{"agents":[]}', {
      status: res.status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  } catch (error: any) {
    const message = error?.message || 'Failed to reach Python server';
    return new Response(JSON.stringify({ error: message, agents: [] }), {
      status: 502,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }
}
