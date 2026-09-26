# lefty-: isolated Arbo sandbox + shared MCP for Claude and Grok

This repo is where Claude and Grok build a **sandbox version of Arbo** without
touching live Arbo, real customers or real accounts.

| Path | What it is |
|---|---|
| `sandbox/` | A copy of `artistreellc/Arbo` @ `940caa9`. It runs on **fake SIM data only**. |
| `sandbox/isolation/` | The lock that keeps it isolated, plus the tests that prove it. |
| `mcp/` | An MCP server that gives Claude and Grok the same context and a shared board. |
| `mcp/BRIEF.md` | The ground rules every agent reads first (the `arbo_brief` tool). |
| `board/` | Shared tasks and handoff log, written by the MCP server. |
| `arbo-mcp/` | **Separate build from Grok Bot's Arbo Dream Brief handoff:** Arbo's own three-tool test MCP server (Python standard library only; synthetic data; deploys nothing). See `arbo-mcp/README.md` and `arbo-mcp/REVIEW_FOR_MIKE.md`. |

## Isolation (Mike, 2026-09-26: "keep it isolated")

`sandbox/isolation/lock.mjs` loads before any Arbo code, both when the app runs
and in every test:

- Every credential Arbo reads is blanked, so Supabase, Quo, Gmail, Calendar,
  Drive, Twilio, ElevenLabs, Resend and Anthropic all report "not configured".
- Data links can never be `live`: they are `sim` when running and cut under tests.
- Outbound network is blocked (fetch, WebSocket, http/https). Only loopback
  (this machine) is allowed.
- It refuses to boot if a deploy-carried `private/deploy.config.json` appears.

Beyond the lock:

- Nothing in this repo deploys.
- The MCP server has **no** tool that writes code, runs commands or reaches a
  live service.
- Its HTTP mode binds to `127.0.0.1` by default and always requires a token.

## Run the sandbox

```sh
cd sandbox
npm ci
npm run check     # typecheck + lint + 1,356 tests (incl. isolation)
npm run serve     # http://127.0.0.1:8787/ on SIM data
```

## Run the MCP server

```sh
cd mcp
npm ci
npm run check     # typecheck + tests
```

- **Claude Code**: `.mcp.json` at the repo root registers it as `lefty-arbo`
  over stdio. Run `cd mcp && npm ci` once first.
- **Grok / any remote client** uses HTTP:

  ```sh
  cd mcp
  LEFTY_MCP_TOKEN=<32+ random chars> npm run start:http
  # → http://127.0.0.1:8765/mcp, header: Authorization: Bearer <token>
  ```

  This listens on this machine only. For Grok to reach it from xAI's side,
  it has to be exposed at a public URL. That is a separate decision for Mike
  and has not been made.

## Tools

| Tool | What it does |
|---|---|
| `arbo_brief` | Ground rules: isolation, SLOW::ARBO, non-negotiables, read order, how the board works |
| `list_docs` / `read_doc` | Arbo's docs in read order (CLAUDE.md, OWNER_RULINGS, DECISIONS, spec…) |
| `get_policy` | `guardrails`, `compliance` or `inbox_intents` JSON |
| `list_files` / `read_file` / `search_code` | Read-only access to `sandbox/`. `.env`, `private/`, `node_modules/` and `.git/` are never readable. |
| `board_list` / `board_create_task` / `board_update_task` | Shared tasks. Only Mike sets `done`. |
| `board_post_handoff` / `board_read_handoffs` | Notes between Claude, Grok and Mike |
