# lefty-: read before touching anything

This repo is the **isolated Arbo sandbox** that Claude and Grok build in.
Mike owns it. Mike, 2026-09-26: **"keep it isolated."**

1. Read `mcp/BRIEF.md` first, then `sandbox/CLAUDE.md` (the sandbox override
   at its top, then Arbo's own rules, including SLOW::ARBO).
2. **Never deploy, never touch live Supabase or any live service, and never
   push to `artistreellc/Arbo`.** The Railway/Supabase IDs in
   `sandbox/CLAUDE.md` belong to LIVE Arbo.
3. Do not weaken `sandbox/isolation/lock.mjs`. Keep
   `sandbox/isolation/isolation.test.ts` green.
4. Before handing off: run `npm run check` in `sandbox/` (and in `mcp/` if you
   touched it).
5. Coordinate through the `lefty-arbo` MCP board. Only Mike sets `done`.
