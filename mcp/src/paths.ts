import { existsSync, realpathSync } from 'node:fs';
import { basename, dirname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

/** Repo root of lefty- (mcp/src → ../..). */
export const REPO_ROOT = resolve(here, '..', '..');

export interface Roots {
  /** The isolated Arbo sandbox copy. Everything readable lives under here. */
  sandboxRoot: string;
  /** Where the shared task board + handoff log are stored. */
  boardDir: string;
  /** The brief every agent reads first. */
  briefPath: string;
}

export function defaultRoots(): Roots {
  return {
    sandboxRoot: resolve(REPO_ROOT, 'sandbox'),
    boardDir: resolve(REPO_ROOT, 'board'),
    briefPath: resolve(REPO_ROOT, 'mcp', 'BRIEF.md'),
  };
}

/** Directory names never listed, searched, or read. */
const DENIED_DIRS = new Set(['node_modules', '.git', 'private', 'dist', 'coverage']);

/** File names never read — anything that could hold a credential. */
function deniedFile(name: string): boolean {
  const n = name.toLowerCase();
  if (n.startsWith('.env') && n !== '.env.example') return true;
  if (n.endsWith('.pem') || n.endsWith('.key')) return true;
  if (n.startsWith('service-account') || n.startsWith('credentials')) return true;
  if (n.startsWith('google-') && n.endsWith('.json')) return true;
  return false;
}

export function isDeniedDir(name: string): boolean {
  return DENIED_DIRS.has(name);
}

export function isDeniedFile(name: string): boolean {
  return deniedFile(name);
}

export class PathRefusedError extends Error {
  constructor(path: string, why: string) {
    super(`Refused "${path}": ${why}`);
    this.name = 'PathRefusedError';
  }
}

/**
 * Resolve a caller-supplied path to an absolute path INSIDE the sandbox, or
 * throw. Symlinks are resolved first, so a link pointing outside is refused.
 */
export function confine(sandboxRoot: string, userPath: string): string {
  // A leading "/" is treated as sandbox-relative ("/src/x.ts" → src/x.ts).
  const cleaned = (userPath ?? '').trim().replace(/^\/+/, '') || '.';
  const target = resolve(sandboxRoot, cleaned);
  const root = realpathSync(sandboxRoot);
  const real = existsSync(target) ? realpathSync(target) : target;
  if (real !== root && !real.startsWith(root + sep)) {
    throw new PathRefusedError(userPath, 'outside the sandbox');
  }
  const rel = relative(root, real);
  for (const part of rel.split(sep)) {
    if (isDeniedDir(part)) throw new PathRefusedError(userPath, `"${part}" is never readable`);
  }
  if (rel && isDeniedFile(basename(real))) {
    throw new PathRefusedError(userPath, 'files that can hold credentials are never readable');
  }
  return real;
}

export function toSandboxRelative(sandboxRoot: string, abs: string): string {
  return relative(realpathSync(sandboxRoot), abs).split(sep).join('/') || '.';
}
