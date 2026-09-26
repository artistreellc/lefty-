# Arbo Sandbox — brief for Claude and Grok

Read this at the start of every session. Mike owns this project; you build.

## What you are working on

**Arbo** is Mike's AI reception and operations platform for Art-is-Tree LLC,
a tree-care company in Hampton Roads, VA. It answers the phone, qualifies and
books work, handles permitting paperwork, and covers for Mike in the field.
Live Arbo is `artistreellc/Arbo`.

**This repo (`artistreellc/lefty-`) holds an isolated SANDBOX copy** of Arbo
(`sandbox/`, copied from Arbo @ `940caa9`). Claude and Grok build here. Live
Arbo is never touched from here.

## Isolation — Mike, 2026-09-26: "keep it isolated"

- The sandbox runs on **fake SIM data only**: `SIM-` names, `555-01xx`
  numbers, and streets that do not exist.
- **No live services**: no Supabase, Quo, Gmail, Calendar, Drive, Twilio,
  ElevenLabs, Resend, Anthropic, Railway or Vercel. `sandbox/isolation/lock.mjs`
  enforces this in code. It blanks credentials, keeps data links from ever
  being `live`, and blocks outbound network.
- **Never deploy** from this repo. **Never push to `artistreellc/Arbo`.**
- The live Railway/Supabase IDs in `sandbox/CLAUDE.md` belong to LIVE Arbo.
  They are not yours to use.
- Removing or weakening the lock is Mike's decision, never yours.
  `sandbox/isolation/isolation.test.ts` must stay green.

## SLOW::ARBO (Mike's standing instruction, in Arbo since 2026-08-03)

1. Read every line of a file before you edit one.
2. An audit is read-only. Report findings; do not fix them.
3. Think before you type. Most things that look wrong are a deliberate
   correction, so check `docs/OWNER_RULINGS.md` first.
4. **Bring it to Mike. Do not decide it.** Anything wrong, ambiguous or
   outside the ask gets flagged, and then you wait.
5. Do exactly what was asked. No adjacent work, no cleanup, no bigger idea.

## Arbo's non-negotiables (enforced in code)

- The service area is exactly **Virginia Beach, Norfolk, Chesapeake and
  Portsmouth**. Suffolk is never served or mentioned.
- Never give a price over the phone, and never diagnose a tree over the phone.
- Credentials: licensed and insured, BBB A+. **Never claim TCIA.**
- **Never autonomous**: ARBO proposes and Mike approves.
- §1B: a dead feed is **named**, never shown as a confident zero.
- The source of truth is `src/policy/guardrails.json` and
  `src/legal/compliance.json` (use the `get_policy` tool).
- The currently approved scope is **receptionist + permitting**. Everything
  else is parked. New scope goes on the board as `needs_mike`; it is never
  built silently.

## Read order (use `list_docs` / `read_doc`)

1. `CLAUDE.md` (the sandbox override at the top, then Arbo's own rules)
2. `docs/OWNER_RULINGS.md`: things that look like bugs and are not
3. `DECISIONS.md`: the decision log, newest at the bottom
4. `docs/ARBO_SPEC.md`, `docs/GAMEPLAN.md`

## How to work

- The code lives in `sandbox/`: `cd sandbox && npm ci && npm run check`
  (typecheck, lint, tests). It must be green before you hand anything off.
- To run the app locally on SIM data: `npm run serve`, then open
  `http://127.0.0.1:8787/` (or whatever `PORT` you set).
- Tests come first. Keep changes small, and review your own diff adversarially.
- Changes land as **PRs to `artistreellc/lefty-`**, and Mike merges them.

## The board (shared between Claude, Grok and Mike)

- `board_list`: see what is open and who owns it.
- `board_create_task` / `board_update_task`: statuses are `open`,
  `in_progress`, `review`, `needs_mike` and `done`. **Only Mike sets `done`.**
  Finished work goes to `review`, and questions go to `needs_mike`.
- `board_post_handoff` / `board_read_handoffs`: leave the other agent a note
  covering what you did, what is next and what you need. Read yours at the
  start of a session.
- Sign every write with your own name (`claude`, `grok` or `mike`). Never
  sign as someone else.
