// The shared board: tasks + a handoff log that Claude, Grok and Mike all see.
// Stored as plain files under board/ so it is also visible (and reviewable)
// in git.
//
// Rule carried from Arbo ("ARBO proposes; Mike approves"): an agent can move
// a task to `review` or `needs_mike`, but only Mike can mark it `done`.
// The author field is self-declared — this is a working convention between
// the bots, not an access control.

import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const AUTHORS = ['claude', 'grok', 'mike'] as const;
export type Author = (typeof AUTHORS)[number];

export const STATUSES = ['open', 'in_progress', 'review', 'needs_mike', 'done'] as const;
export type Status = (typeof STATUSES)[number];

export interface Note {
  at: string;
  author: Author;
  text: string;
  status?: Status;
}

export interface Task {
  id: number;
  title: string;
  detail: string;
  status: Status;
  owner: Author | null;
  createdBy: Author;
  createdAt: string;
  updatedAt: string;
  notes: Note[];
}

export interface Handoff {
  at: string;
  from: Author;
  to: Author | 'all';
  message: string;
  taskId?: number;
}

interface TaskFile {
  nextId: number;
  tasks: Task[];
}

export class BoardError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BoardError';
  }
}

export class Board {
  private readonly tasksPath: string;
  private readonly handoffsPath: string;

  constructor(private readonly dir: string, private readonly now: () => Date = () => new Date()) {
    this.tasksPath = join(dir, 'tasks.json');
    this.handoffsPath = join(dir, 'handoffs.jsonl');
  }

  listTasks(filter: { status?: Status; owner?: Author } = {}): Task[] {
    return this.load().tasks.filter(
      (t) => (!filter.status || t.status === filter.status) && (!filter.owner || t.owner === filter.owner),
    );
  }

  getTask(id: number): Task {
    const task = this.load().tasks.find((t) => t.id === id);
    if (!task) throw new BoardError(`No task #${id}`);
    return task;
  }

  createTask(input: { title: string; detail?: string; author: Author; owner?: Author | null }): Task {
    const title = input.title.trim();
    if (!title) throw new BoardError('A task needs a title');
    const data = this.load();
    const at = this.now().toISOString();
    const task: Task = {
      id: data.nextId,
      title,
      detail: (input.detail ?? '').trim(),
      status: 'open',
      owner: input.owner ?? null,
      createdBy: input.author,
      createdAt: at,
      updatedAt: at,
      notes: [],
    };
    data.nextId += 1;
    data.tasks.push(task);
    this.save(data);
    return task;
  }

  updateTask(input: { id: number; author: Author; status?: Status; owner?: Author | null; note?: string }): Task {
    if (input.status === 'done' && input.author !== 'mike') {
      throw new BoardError('Only Mike marks a task done. Move it to "review" and hand it to Mike.');
    }
    const data = this.load();
    const task = data.tasks.find((t) => t.id === input.id);
    if (!task) throw new BoardError(`No task #${input.id}`);
    if (task.status === 'done' && input.author !== 'mike') {
      throw new BoardError(`Task #${task.id} is done — only Mike can reopen or change it.`);
    }
    const text = (input.note ?? '').trim();
    if (!text && input.status === undefined && input.owner === undefined) {
      throw new BoardError('Nothing to update: give a status, an owner, or a note');
    }
    const at = this.now().toISOString();
    if (input.status) task.status = input.status;
    if (input.owner !== undefined) task.owner = input.owner;
    if (text || input.status) task.notes.push({ at, author: input.author, text, ...(input.status ? { status: input.status } : {}) });
    task.updatedAt = at;
    this.save(data);
    return task;
  }

  postHandoff(input: { from: Author; to: Author | 'all'; message: string; taskId?: number }): Handoff {
    const message = input.message.trim();
    if (!message) throw new BoardError('A handoff needs a message');
    if (input.taskId !== undefined) this.getTask(input.taskId);
    const entry: Handoff = {
      at: this.now().toISOString(),
      from: input.from,
      to: input.to,
      message,
      ...(input.taskId !== undefined ? { taskId: input.taskId } : {}),
    };
    this.ensureDir();
    appendFileSync(this.handoffsPath, `${JSON.stringify(entry)}\n`);
    return entry;
  }

  /** Newest last. `to` includes messages addressed to 'all'. */
  readHandoffs(filter: { to?: Author; limit?: number } = {}): Handoff[] {
    if (!existsSync(this.handoffsPath)) return [];
    const all = readFileSync(this.handoffsPath, 'utf8')
      .split('\n')
      .filter((l) => l.trim())
      .map((l) => JSON.parse(l) as Handoff)
      .filter((h) => !filter.to || h.to === filter.to || h.to === 'all');
    const limit = Math.min(Math.max(1, filter.limit ?? 20), 200);
    return all.slice(-limit);
  }

  private load(): TaskFile {
    if (!existsSync(this.tasksPath)) return { nextId: 1, tasks: [] };
    return JSON.parse(readFileSync(this.tasksPath, 'utf8')) as TaskFile;
  }

  /** Write-then-rename, so a crash mid-write never leaves a torn file. */
  private save(data: TaskFile): void {
    this.ensureDir();
    const tmp = `${this.tasksPath}.tmp`;
    writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`);
    renameSync(tmp, this.tasksPath);
  }

  private ensureDir(): void {
    if (!existsSync(this.dir)) mkdirSync(this.dir, { recursive: true });
  }
}
