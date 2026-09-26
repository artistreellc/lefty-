// HTTP entry point: MCP over Streamable HTTP at POST /mcp (stateless).
// This is the transport a remote client such as Grok needs.
//
// ISOLATED BY DEFAULT: binds to 127.0.0.1 only. Exposing it beyond this
// machine (a public host, a tunnel, a deploy) is Mike's call — set
// LEFTY_MCP_HOST explicitly only when he has made it.
//
// A bearer token is ALWAYS required: LEFTY_MCP_TOKEN, at least 32 chars.

import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createLeftyServer } from './server.js';
import { defaultRoots, type Roots } from './paths.js';

const MAX_BODY_BYTES = 1_000_000;

export function tokenMatches(expected: string, header: string | undefined): boolean {
  const got = header?.startsWith('Bearer ') ? header.slice(7) : '';
  const a = Buffer.from(expected);
  const b = Buffer.from(got);
  return a.length === b.length && timingSafeEqual(a, b);
}

function send(res: ServerResponse, code: number, body: unknown): void {
  res.writeHead(code, { 'content-type': 'application/json' }).end(JSON.stringify(body));
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY_BYTES) throw new Error('body too large');
    chunks.push(chunk as Buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || 'null');
}

export function createHttpHandler(token: string, roots: Roots = defaultRoots()) {
  if (token.length < 32) throw new Error('LEFTY_MCP_TOKEN must be at least 32 characters');
  return async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    const url = new URL(req.url ?? '/', 'http://localhost');
    if (url.pathname === '/health') return send(res, 200, { ok: true });
    if (url.pathname !== '/mcp') return send(res, 404, { error: 'not found' });
    if (!tokenMatches(token, req.headers.authorization)) return send(res, 401, { error: 'unauthorized' });
    if (req.method !== 'POST') {
      // Stateless server: no standalone SSE stream, no session to delete.
      return send(res, 405, { jsonrpc: '2.0', error: { code: -32000, message: 'Method not allowed' }, id: null });
    }
    let body: unknown;
    try {
      body = await readJson(req);
    } catch (err) {
      return send(res, 400, { jsonrpc: '2.0', error: { code: -32700, message: err instanceof Error ? err.message : 'bad body' }, id: null });
    }
    // Stateless: a fresh server + transport per request.
    const server = createLeftyServer(roots);
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    res.on('close', () => {
      void transport.close();
      void server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, body);
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const token = process.env.LEFTY_MCP_TOKEN ?? '';
  const host = process.env.LEFTY_MCP_HOST ?? '127.0.0.1';
  const port = Number(process.env.LEFTY_MCP_PORT ?? 8765);
  const handler = createHttpHandler(token);
  createServer((req, res) => {
    handler(req, res).catch((err: unknown) => {
      console.error('[lefty-mcp] request failed:', err instanceof Error ? err.message : err);
      if (!res.headersSent) send(res, 500, { error: 'internal error' });
    });
  }).listen(port, host, () => {
    console.log(`lefty MCP on http://${host}:${port}/mcp (bearer token required)`);
  });
}
