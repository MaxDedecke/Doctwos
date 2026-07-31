import { NextRequest } from 'next/server';

// Internal Docker hostname — reachable server-side from the frontend container.
// Falls back to the public API_URL if INTERNAL_API_URL is not set.
const BACKEND = (process.env.INTERNAL_API_URL || process.env.API_URL || 'http://backend-api:8000').replace(/\/$/, '');

export async function POST(req: NextRequest) {
    const body = await req.text();

    // Forward the session cookie. The browser sends it here because this is a
    // same-origin request (frontend port 3000 → frontend port 3000). We then
    // manually attach it to the upstream backend call, working around the
    // SameSite=Lax + CORS-preflight block that prevents the browser from sending
    // it directly to the backend on port 8000.
    const sessionCookie = req.cookies.get('doctus_session');
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    if (sessionCookie) {
        headers['Cookie'] = `doctus_session=${sessionCookie.value}`;
    }

    const upstream = await fetch(`${BACKEND}/chat`, {
        method: 'POST',
        headers,
        body,
    });

    return new Response(upstream.body, {
        status: upstream.status,
        headers: {
            'Content-Type': upstream.headers.get('Content-Type') ?? 'text/event-stream',
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    });
}
