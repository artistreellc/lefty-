// Read-only views of the Arbo sandbox: docs, policy, files, search.
// Nothing in this file writes anywhere.

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';
import { confine, isDeniedDir, isDeniedFile, toSandboxRelative } from './paths.js';

const MAX_FILE_BYTES = 1_000_000;
const BINARY_EXT = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.zip', '.woff', '.woff2', '.ttf']);

/** Read these first, in this order — the order Arbo's own CLAUDE.md sets. */
const READ_FIRST = ['CLAUDE.md', 'docs/OWNER_RULINGS.md', 'DECISIONS.md', 'docs/ARBO_SPEC.md', 'docs/GAMEPLAN.md', 'README.md', 'PROGRESS.md'];

/** Every markdown doc: the read-first list, then the rest of docs/ alphabetically. */
export function listDocs(sandboxRoot: string): string[] {
  const first = READ_FIRST.filter((d) => safeExists(join(sandboxRoot, d)));
  const docsDir = join(sandboxRoot, 'docs');
  const rest = safeExists(docsDir)
    ? readdirSync(docsDir, { withFileTypes: true })
        .filter((e) => e.isFile() && e.name.endsWith('.md'))
        .map((e) => `docs/${e.name}`)
        .filter((d) => !first.includes(d))
        .sort()
    : [];
  return [...first, ...rest];
}

export interface Paged {
  path: string;
  totalLines: number;
  fromLine: number;
  toLine: number;
  text: string;
}

/** Read a text file inside the sandbox, paged by line (1-based). */
export function readPaged(sandboxRoot: string, path: string, fromLine = 1, maxLines = 400): Paged {
  const abs = confine(sandboxRoot, path);
  const st = statSync(abs);
  if (st.isDirectory()) throw new Error(`"${path}" is a directory — use list_files`);
  if (BINARY_EXT.has(extname(abs).toLowerCase())) throw new Error(`"${path}" is a binary file`);
  if (st.size > MAX_FILE_BYTES) throw new Error(`"${path}" is larger than ${MAX_FILE_BYTES} bytes`);
  const lines = readFileSync(abs, 'utf8').split('\n');
  const start = Math.max(1, Math.floor(fromLine));
  const count = Math.min(Math.max(1, Math.floor(maxLines)), 2000);
  const slice = lines.slice(start - 1, start - 1 + count);
  return {
    path: toSandboxRelative(sandboxRoot, abs),
    totalLines: lines.length,
    fromLine: start,
    toLine: start - 1 + slice.length,
    text: slice.map((l, i) => `${String(start + i).padStart(5)}  ${l}`).join('\n'),
  };
}

export type PolicyName = 'guardrails' | 'compliance' | 'inbox_intents';
const POLICY_FILES: Record<PolicyName, string> = {
  guardrails: 'src/policy/guardrails.json',
  compliance: 'src/legal/compliance.json',
  inbox_intents: 'src/policy/inboxIntents.json',
};

export function readPolicy(sandboxRoot: string, name: PolicyName): string {
  return readFileSync(confine(sandboxRoot, POLICY_FILES[name]), 'utf8');
}

export interface Entry {
  path: string;
  type: 'dir' | 'file';
  bytes?: number;
}

export function listFiles(sandboxRoot: string, dir = '.'): Entry[] {
  const abs = confine(sandboxRoot, dir);
  if (!statSync(abs).isDirectory()) throw new Error(`"${dir}" is not a directory`);
  return readdirSync(abs, { withFileTypes: true })
    .filter((e) => (e.isDirectory() ? !isDeniedDir(e.name) : !isDeniedFile(e.name)))
    .map((e): Entry => {
      const p = toSandboxRelative(sandboxRoot, resolve(abs, e.name));
      return e.isDirectory() ? { path: `${p}/`, type: 'dir' } : { path: p, type: 'file', bytes: statSync(resolve(abs, e.name)).size };
    })
    .sort((a, b) => (a.type === b.type ? a.path.localeCompare(b.path) : a.type === 'dir' ? -1 : 1));
}

export interface Hit {
  path: string;
  line: number;
  text: string;
}

/** Regex search over sandbox text files. Case-insensitive; capped. */
export function searchCode(sandboxRoot: string, pattern: string, under = '.', maxHits = 100): { hits: Hit[]; truncated: boolean } {
  let re: RegExp;
  try {
    re = new RegExp(pattern, 'i');
  } catch (err) {
    throw new Error(`Invalid regex: ${err instanceof Error ? err.message : String(err)}`);
  }
  const hits: Hit[] = [];
  const cap = Math.min(Math.max(1, maxHits), 500);
  let truncated = false;

  const walk = (dirAbs: string): void => {
    for (const e of readdirSync(dirAbs, { withFileTypes: true })) {
      if (truncated) return;
      const abs = join(dirAbs, e.name);
      if (e.isDirectory()) {
        if (!isDeniedDir(e.name)) walk(abs);
        continue;
      }
      if (!e.isFile() || isDeniedFile(e.name) || BINARY_EXT.has(extname(e.name).toLowerCase())) continue;
      if (statSync(abs).size > MAX_FILE_BYTES) continue;
      const lines = readFileSync(abs, 'utf8').split('\n');
      for (let i = 0; i < lines.length; i++) {
        if (re.test(lines[i]!)) {
          if (hits.length >= cap) {
            truncated = true;
            return;
          }
          hits.push({ path: toSandboxRelative(sandboxRoot, abs), line: i + 1, text: lines[i]!.trim().slice(0, 240) });
        }
      }
    }
  };
  const start = confine(sandboxRoot, under);
  if (statSync(start).isDirectory()) walk(start);
  else throw new Error(`"${under}" is not a directory`);
  return { hits, truncated };
}

function safeExists(p: string): boolean {
  try {
    statSync(p);
    return true;
  } catch {
    return false;
  }
}
