// Vercel Edge function: proxies chat completions to Groq for the hosted demo.
// Local users still call Ollama directly from the browser; this only runs when
// the browser falls back to /api/chat because no local Ollama is reachable.

export const config = { runtime: 'edge' };

const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const DEFAULT_MODEL = 'llama-3.3-70b-versatile';
const MAX_INPUT_CHARS = 30000;
const MAX_OUTPUT_TOKENS = 1024;

export default async function handler(req) {
    if (req.method === 'GET') {
        return Response.json({
            available: Boolean(process.env.GROQ_API_KEY),
            model: process.env.GROQ_MODEL || DEFAULT_MODEL,
            provider: 'groq',
        });
    }

    if (req.method !== 'POST') {
        return new Response('Method not allowed', { status: 405 });
    }

    const apiKey = process.env.GROQ_API_KEY;
    if (!apiKey) {
        return Response.json(
            { error: 'GROQ_API_KEY is not configured on this deployment.' },
            { status: 503 },
        );
    }

    let body;
    try {
        body = await req.json();
    } catch {
        return new Response('Invalid JSON', { status: 400 });
    }

    const messages = body && body.messages;
    if (!Array.isArray(messages) || !messages.length) {
        return new Response('messages array is required', { status: 400 });
    }

    const totalChars = messages.reduce(
        (sum, m) => sum + (typeof m?.content === 'string' ? m.content.length : 0),
        0,
    );
    if (totalChars > MAX_INPUT_CHARS) {
        return new Response('Conversation too long', { status: 413 });
    }

    let upstream;
    try {
        upstream = await fetch(GROQ_URL, {
            method: 'POST',
            headers: {
                Authorization: `Bearer ${apiKey}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                model: process.env.GROQ_MODEL || DEFAULT_MODEL,
                messages,
                stream: true,
                temperature: 0.7,
                max_tokens: MAX_OUTPUT_TOKENS,
            }),
        });
    } catch (error) {
        return Response.json(
            { error: 'Upstream fetch failed', detail: String(error).slice(0, 300) },
            { status: 502 },
        );
    }

    if (!upstream.ok || !upstream.body) {
        const detail = await upstream.text().catch(() => '');
        return Response.json(
            { error: 'Upstream model error', status: upstream.status, detail: detail.slice(0, 500) },
            { status: 502 },
        );
    }

    return new Response(upstream.body, {
        headers: {
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
        },
    });
}
