import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { Board } from '../src/board.js';
import { listDocs, listFiles, readPaged, searchCode } from '../src/context.js';
import { createHttpHandler, tokenMatches } from '../src/http.js';
import { confine, defaultRoots, type Roots } from '../src/paths.js';
import { createLeftyServer } from '../src/server.js';

let tmp: string;
let roots: Roots;

beforeAll(() => {
  tmp = mkdtempSync(join(tmpdir(), 'lefty-mcp-'));
  const sb = join(tmp, 'sandbox');
  mkdirSync(join(sb, 'docs'), { recursive: true });
  mkdirSync(join(sb, 'src', 'policy'), { recursive: true });
  mkdirSync(join(sb, 'src', 'legal'), { recursive: true });
  mkdirSync(join(sb, 'node_modules', 'x'), { recursive: true });
  mkdirSync(join(sb, 'private'), { recursive: true });
  writeFileSync(join(sb, 'CLAUDE.md'), '# rules\nline two\n');
  writeFileSync(join(sb, 'DECISIONS.md'), '# decisions\n');
  writeFileSync(join(sb, 'docs', 'OWNER_RULINGS.md'), '# rulings\n');
  writeFileSync(join(sb, 'docs', 'ZETA.md'), '# zeta\n');
  writeFileSync(join(sb, 'src', 'policy', 'guardrails.json'), '{"version":"test"}');
  writeFileSync(join(sb, 'src', 'legal', 'compliance.json'), '{"version":"legal"}');
  writeFileSync(join(sb, 'src', 'a.ts'), 'export const serviceArea = "Norfolk";\n');
  writeFileSync(join(sb, '.env'), 'SUPABASE_SERVICE_ROLE_KEY=sb_secret_REAL\n');
  writeFileSync(join(sb, '.env.example'), 'SUPABASE_URL=\n');
  writeFileSync(join(sb, 'node_modules', 'x', 'i.js'), 'Norfolk');
  writeFileSync(join(sb, 'private', 'deploy.config.json'), '{"k":"Norfolk"}');
  writeFileSync(join(tmp, 'outside.txt'), 'secret outside');
  symlinkSync(join(tmp, 'outside.txt'), join(sb, 'escape.txt'));
  writeFileSync(join(tmp, 'BRIEF.md'), '# brief\nkeep it isolated\n');
  roots = { sandboxRoot: sb, boardDir: join(tmp, 'board'), briefPath: join(tmp, 'BRIEF.md') };
});

afterAll(() => rmSync(tmp, { recursive: true, force: true }));

describe('path confinement', () => {
  it('reads inside the sandbox', () => {
    expect(readPaged(roots.sandboxRoot, 'src/a.ts').text).toContain('Norfolk');
    expect(readPaged(roots.sandboxRoot, '/src/a.ts').path).toBe('src/a.ts');
  });

  it('refuses traversal, symlink escapes, credentials, and hidden dirs', () => {
    const sb = roots.sandboxRoot;
    expect(() => confine(sb, '../outside.txt')).toThrow(/outside the sandbox/);
    expect(() => confine(sb, 'src/../../outside.txt')).toThrow(/outside the sandbox/);
    expect(() => confine(sb, 'escape.txt')).toThrow(/outside the sandbox/);
    expect(() => confine(sb, '.env')).toThrow(/credentials/);
    expect(() => confine(sb, 'private/deploy.config.json')).toThrow(/never readable/);
    expect(() => confine(sb, 'node_modules/x/i.js')).toThrow(/never readable/);
    expect(confine(sb, '.env.example')).toContain('.env.example');
  });

  it('list and search never surface hidden dirs or credential files', () => {
    const names = listFiles(roots.sandboxRoot).map((e) => e.path);
    expect(names).not.toContain('.env');
    expect(names).not.toContain('node_modules/');
    expect(names).not.toContain('private/');
    const { hits } = searchCode(roots.sandboxRoot, 'norfolk|sb_secret');
    expect(hits.map((h) => h.path)).toEqual(['src/a.ts']);
  });

  it('lists docs in read order', () => {
    expect(listDocs(roots.sandboxRoot)).toEqual(['CLAUDE.md', 'docs/OWNER_RULINGS.md', 'DECISIONS.md', 'docs/ZETA.md']);
  });

  it('the real roots point at this repo\'s sandbox', () => {
    const r = defaultRoots();
    expect(listDocs(r.sandboxRoot)).toContain('docs/OWNER_RULINGS.md');
    expect(readPaged(r.sandboxRoot, 'isolation/lock.mjs').text).toContain('SANDBOX ISOLATION LOCK');
  });
});

describe('board', () => {
  it('only Mike marks done, and a done task is frozen for the bots', () => {
    const board = new Board(join(tmp, 'board-rules'));
    const t = board.createTask({ title: 'Wire permit screen', author: 'grok', owner: 'grok' });
    expect(t.id).toBe(1);
    board.updateTask({ id: 1, author: 'grok', status: 'in_progress' });
    expect(() => board.updateTask({ id: 1, author: 'grok', status: 'done' })).toThrow(/Only Mike/);
    expect(() => board.updateTask({ id: 1, author: 'claude', status: 'done' })).toThrow(/Only Mike/);
    board.updateTask({ id: 1, author: 'claude', status: 'review', note: 'checked, tests green' });
    board.updateTask({ id: 1, author: 'mike', status: 'done' });
    expect(board.getTask(1).status).toBe('done');
    expect(() => board.updateTask({ id: 1, author: 'grok', note: 'reopening' })).toThrow(/only Mike/);
    expect(board.getTask(1).notes.map((n) => n.author)).toEqual(['grok', 'claude', 'mike']);
  });

  it('handoffs filter by recipient and include "all"', () => {
    const board = new Board(join(tmp, 'board-handoffs'));
    board.postHandoff({ from: 'claude', to: 'grok', message: 'your turn' });
    board.postHandoff({ from: 'grok', to: 'claude', message: 'done, see PR' });
    board.postHandoff({ from: 'mike', to: 'all', message: 'keep it isolated' });
    expect(board.readHandoffs({ to: 'grok' }).map((h) => h.message)).toEqual(['your turn', 'keep it isolated']);
    expect(() => board.postHandoff({ from: 'grok', to: 'claude', message: 'x', taskId: 99 })).toThrow(/No task/);
  });
});

async function connectInMemory(): Promise<Client> {
  const [clientT, serverT] = InMemoryTransport.createLinkedPair();
  await createLeftyServer(roots).connect(serverT);
  const client = new Client({ name: 'test', version: '0' });
  await client.connect(clientT);
  return client;
}

const text = (r: unknown) => ((r as { content: Array<{ text: string }> }).content[0]!.text);

describe('MCP protocol', () => {
  it('exposes exactly the context + board tools — nothing that writes code, runs commands, or deploys', async () => {
    const client = await connectInMemory();
    const names = (await client.listTools()).tools.map((t) => t.name).sort();
    expect(names).toEqual([
      'arbo_brief', 'board_create_task', 'board_list', 'board_post_handoff', 'board_read_handoffs',
      'board_update_task', 'get_policy', 'list_docs', 'list_files', 'read_doc', 'read_file', 'search_code',
    ]);
  });

  it('serves the brief, docs and policy, and returns refusals as tool errors', async () => {
    const client = await connectInMemory();
    expect(text(await client.callTool({ name: 'arbo_brief', arguments: {} }))).toContain('keep it isolated');
    expect(text(await client.callTool({ name: 'read_doc', arguments: { name: 'docs/OWNER_RULINGS.md' } }))).toContain('rulings');
    expect(text(await client.callTool({ name: 'get_policy', arguments: { which: 'guardrails' } }))).toContain('"test"');
    const refused = await client.callTool({ name: 'read_file', arguments: { path: '.env' } });
    expect(refused.isError).toBe(true);
    expect(text(refused)).not.toContain('sb_secret_REAL');
    const notDoc = await client.callTool({ name: 'read_doc', arguments: { name: 'src/a.ts' } });
    expect(notDoc.isError).toBe(true);
  });

  it('board round-trip through the protocol', async () => {
    const client = await connectInMemory();
    await client.callTool({ name: 'board_create_task', arguments: { title: 'Sandbox task', author: 'claude' } });
    const denied = await client.callTool({ name: 'board_update_task', arguments: { id: 1, author: 'grok', status: 'done' } });
    expect(denied.isError).toBe(true);
    const list = JSON.parse(text(await client.callTool({ name: 'board_list', arguments: {} }))) as Array<{ title: string }>;
    expect(list.map((t) => t.title)).toContain('Sandbox task');
  });
});

describe('HTTP transport', () => {
  const token = 't'.repeat(40);
  let server: Server;
  let base: string;

  beforeAll(async () => {
    const handler = createHttpHandler(token, roots);
    server = createServer((req, res) => void handler(req, res));
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r));
    base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  });
  afterAll(() => server.close());

  it('refuses a short token at startup', () => {
    expect(() => createHttpHandler('short')).toThrow(/at least 32/);
  });

  it('compares tokens exactly', () => {
    expect(tokenMatches(token, `Bearer ${token}`)).toBe(true);
    expect(tokenMatches(token, `Bearer ${token}x`)).toBe(false);
    expect(tokenMatches(token, token)).toBe(false);
    expect(tokenMatches(token, undefined)).toBe(false);
  });

  it('rejects requests without the bearer token', async () => {
    const res = await fetch(`${base}/mcp`, { method: 'POST', body: '{}', headers: { 'content-type': 'application/json' } });
    expect(res.status).toBe(401);
  });

  it('serves the tools to an authorised MCP client', async () => {
    const client = new Client({ name: 'grok-sim', version: '0' });
    await client.connect(new StreamableHTTPClientTransport(new URL(`${base}/mcp`), {
      requestInit: { headers: { authorization: `Bearer ${token}` } },
    }));
    expect((await client.listTools()).tools.length).toBe(12);
    expect(text(await client.callTool({ name: 'arbo_brief', arguments: {} }))).toContain('keep it isolated');
    await client.close();
  });
});
