// lefty- MCP server: shared context for Claude + Grok building the isolated
// Arbo sandbox. Two kinds of tools:
//
//   CONTEXT (read-only)  — the brief, Arbo's docs/rulings, policy JSON, and
//                          the sandbox code. Confined to sandbox/; files that
//                          can hold credentials are never readable.
//   BOARD (shared)       — tasks + handoff log, so the bots can pass work.
//
// There is deliberately NO tool that writes code, runs commands, deploys, or
// touches a live service. Code changes go through git as PRs Mike reviews.

import { readFileSync } from 'node:fs';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import { AUTHORS, Board, STATUSES } from './board.js';
import { listDocs, listFiles, readPaged, readPolicy, searchCode } from './context.js';
import { defaultRoots, type Roots } from './paths.js';

type ToolResult = { content: Array<{ type: 'text'; text: string }>; isError?: boolean };

const ok = (value: unknown): ToolResult => ({
  content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }],
});

/** Every handler runs through this, so a bad path or rule breach comes back as a readable tool error. */
function guarded<A>(fn: (args: A) => unknown): (args: A) => Promise<ToolResult> {
  return async (args: A) => {
    try {
      return ok(await fn(args));
    } catch (err) {
      return { content: [{ type: 'text', text: err instanceof Error ? err.message : String(err) }], isError: true };
    }
  };
}

const author = z.enum(AUTHORS).describe('Who is acting: claude, grok, or mike');
const status = z.enum(STATUSES);

export function createLeftyServer(roots: Roots = defaultRoots()): McpServer {
  const { sandboxRoot, boardDir, briefPath } = roots;
  const board = new Board(boardDir);
  const server = new McpServer({ name: 'lefty-arbo-sandbox', version: '0.1.0' });

  // ── CONTEXT ────────────────────────────────────────────────────────────
  server.registerTool(
    'arbo_brief',
    {
      title: 'Read this first',
      description:
        'The ground rules for working on the Arbo sandbox: what Arbo is, the isolation rules, SLOW::ARBO, the read order, and how the board works. Call this before anything else in a new session.',
      inputSchema: {},
    },
    guarded(() => readFileSync(briefPath, 'utf8')),
  );

  server.registerTool(
    'list_docs',
    {
      title: 'List Arbo docs',
      description: 'Every Arbo markdown doc, in the order to read them (CLAUDE.md, OWNER_RULINGS, DECISIONS, spec, gameplan, then the rest).',
      inputSchema: {},
    },
    guarded(() => listDocs(sandboxRoot)),
  );

  server.registerTool(
    'read_doc',
    {
      title: 'Read an Arbo doc',
      description: 'Read one doc from list_docs, paged by line. Long docs (DECISIONS.md, PROGRESS.md) need several pages.',
      inputSchema: {
        name: z.string().describe('A path from list_docs, e.g. "docs/OWNER_RULINGS.md"'),
        from_line: z.number().int().min(1).optional().describe('1-based line to start at (default 1)'),
        max_lines: z.number().int().min(1).max(2000).optional().describe('Lines to return (default 400)'),
      },
    },
    guarded(({ name, from_line, max_lines }: { name: string; from_line?: number; max_lines?: number }) => {
      if (!listDocs(sandboxRoot).includes(name)) throw new Error(`"${name}" is not an Arbo doc — call list_docs`);
      return readPaged(sandboxRoot, name, from_line, max_lines);
    }),
  );

  server.registerTool(
    'get_policy',
    {
      title: 'Get Arbo policy JSON',
      description:
        'The single-source-of-truth policy files: guardrails (never price, never diagnose, service area…), compliance (legal/TCPA), or inbox_intents.',
      inputSchema: { which: z.enum(['guardrails', 'compliance', 'inbox_intents']) },
    },
    guarded(({ which }: { which: 'guardrails' | 'compliance' | 'inbox_intents' }) => readPolicy(sandboxRoot, which)),
  );

  server.registerTool(
    'list_files',
    {
      title: 'List sandbox files',
      description: 'List a directory in the sandbox (default: the sandbox root). node_modules, .git, private and credential files are hidden.',
      inputSchema: { dir: z.string().optional().describe('Sandbox-relative directory, e.g. "src/reception"') },
    },
    guarded(({ dir }: { dir?: string }) => listFiles(sandboxRoot, dir)),
  );

  server.registerTool(
    'read_file',
    {
      title: 'Read a sandbox file',
      description: 'Read any text file in the sandbox, paged by line with line numbers.',
      inputSchema: {
        path: z.string().describe('Sandbox-relative path, e.g. "src/reception/receptionist.ts"'),
        from_line: z.number().int().min(1).optional(),
        max_lines: z.number().int().min(1).max(2000).optional(),
      },
    },
    guarded(({ path, from_line, max_lines }: { path: string; from_line?: number; max_lines?: number }) =>
      readPaged(sandboxRoot, path, from_line, max_lines)),
  );

  server.registerTool(
    'search_code',
    {
      title: 'Search the sandbox',
      description: 'Case-insensitive regex search across sandbox text files. Returns path, line and the matching line.',
      inputSchema: {
        pattern: z.string().min(1).describe('JavaScript regex, e.g. "dataLinksSim|ARBO_DATA_LINKS"'),
        under: z.string().optional().describe('Limit to a sandbox-relative directory (default: whole sandbox)'),
        max_hits: z.number().int().min(1).max(500).optional().describe('Default 100'),
      },
    },
    guarded(({ pattern, under, max_hits }: { pattern: string; under?: string; max_hits?: number }) =>
      searchCode(sandboxRoot, pattern, under, max_hits)),
  );

  // ── BOARD ──────────────────────────────────────────────────────────────
  server.registerTool(
    'board_list',
    {
      title: 'List board tasks',
      description: 'Tasks on the shared board, optionally filtered by status or owner.',
      inputSchema: { status: status.optional(), owner: z.enum(AUTHORS).optional() },
    },
    guarded((f: { status?: (typeof STATUSES)[number]; owner?: (typeof AUTHORS)[number] }) => board.listTasks(f)),
  );

  server.registerTool(
    'board_create_task',
    {
      title: 'Create a board task',
      description: 'Add a task to the shared board. New scope not already approved by Mike should be created and moved to needs_mike, not built.',
      inputSchema: {
        title: z.string().min(1),
        detail: z.string().optional(),
        author,
        owner: z.enum(AUTHORS).optional().describe('Who will do it (optional)'),
      },
    },
    guarded((a: { title: string; detail?: string; author: (typeof AUTHORS)[number]; owner?: (typeof AUTHORS)[number] }) =>
      board.createTask(a)),
  );

  server.registerTool(
    'board_update_task',
    {
      title: 'Update a board task',
      description:
        'Change a task\'s status and/or owner, and/or add a note. Statuses: open, in_progress, review, needs_mike, done. Only Mike can set done.',
      inputSchema: {
        id: z.number().int().min(1),
        author,
        status: status.optional(),
        owner: z.enum(AUTHORS).nullable().optional(),
        note: z.string().optional(),
      },
    },
    guarded((a: {
      id: number;
      author: (typeof AUTHORS)[number];
      status?: (typeof STATUSES)[number];
      owner?: (typeof AUTHORS)[number] | null;
      note?: string;
    }) => board.updateTask(a)),
  );

  server.registerTool(
    'board_post_handoff',
    {
      title: 'Post a handoff',
      description: 'Leave a message for another agent (or everyone): what you did, what is next, what you need.',
      inputSchema: {
        from: author,
        to: z.enum([...AUTHORS, 'all']),
        message: z.string().min(1),
        task_id: z.number().int().min(1).optional(),
      },
    },
    guarded((a: { from: (typeof AUTHORS)[number]; to: (typeof AUTHORS)[number] | 'all'; message: string; task_id?: number }) =>
      board.postHandoff({ from: a.from, to: a.to, message: a.message, ...(a.task_id !== undefined ? { taskId: a.task_id } : {}) })),
  );

  server.registerTool(
    'board_read_handoffs',
    {
      title: 'Read handoffs',
      description: 'Recent handoff messages, newest last. Filter to messages for you (includes ones sent to "all").',
      inputSchema: {
        to: z.enum(AUTHORS).optional(),
        limit: z.number().int().min(1).max(200).optional().describe('Default 20'),
      },
    },
    guarded((f: { to?: (typeof AUTHORS)[number]; limit?: number }) => board.readHandoffs(f)),
  );

  return server;
}
