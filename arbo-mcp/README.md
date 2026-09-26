# Arbo MCP

**Project name (Mike, Sep 26, 2026): Arbo MCP.** First sandboxed build: the
test tool server, plus the app's skin template.

Built by Claude Code, Sep 26, 2026, from the Grok Bot handoff (v2) and
*Arbo_Dream_Brief.md*. **Test setup only.** Synthetic data. It deploys nothing.

**Where it lives (Mike, Sep 26, 2026):** "Make sure it is in a sandbox on
GitHub." It's in `artistreellc/lefty-` under `arbo-mcp/`. This replaces the
handoff's rule 1 ("no git remote, no GitHub, ever") on Mike's direct
instruction.

## What it is

A minimal MCP tool server with **exactly three tools**:

| Tool | What it does |
|---|---|
| `read_logs` | Read-only. Filters the synthetic test logs in `data/synthetic_logs.jsonl`. |
| `read_errors` | Read-only. Reads a synthetic stand-in for error reports (`data/synthetic_errors.json`). It doesn't connect to Sentry. |
| `deploy` | Asks Mike yes or no and waits. **Only an explicit "yes" counts**, and no answer counts as no. **It deploys nothing.** It records the request and the answer. |

There are no other tools, no resources or prompts, and no hidden permissions.
Every message the server receives is logged **before** it's acted on, and
**if the log can't be written, the call is refused**.

## How `deploy` asks Mike

It uses the MCP standard's "elicitation" request (`elicitation/create`): the
server asks the MCP client to show a yes/no question to the person using it.

- `accept` with the answer `yes` means **yes**.
- Everything else means **no**: decline, cancel, accept without "yes", an
  error, a malformed answer, a client that can't show questions, a
  disconnect, or **no answer before the timeout** (default 120 seconds,
  `--deploy-timeout`).
- A "yes" that arrives after the timeout is logged and ignored.
- **Every answer is recorded as "identity not verified."** The client prompt
  can't prove Mike is the one answering. See `REVIEW_FOR_MIKE.md`.

## Rules followed

- **Python standard library only.** Nothing was installed, so there's no
  package list to approve.
- **No network code.** Tests check the imports, check for web addresses, and
  run the real server with the Python interpreter itself blocking every
  network and process-launch event.
- **Cut off from all links** (Mike, Sep 26, 2026). There are no web
  addresses, domain names, IP addresses or emails in the code, data or skin,
  no import from outside the standard library, and the skin loads only its
  own files. `tests/test_isolation.py` fails the build if any of that
  changes.
- **Synthetic data only.** Everything is tagged `SIM`, and tests check for
  phone numbers and email addresses.
- Built in a fresh local folder, then placed in the `lefty-` sandbox repo on
  GitHub at Mike's direction (above). Rollback is through that repo's history.

## Files

```
arbo_mcp/server.py    stdio JSON-RPC loop, logging, the deploy question
arbo_mcp/tools.py     the three tools, argument checks, yes/no rule
arbo_mcp/calllog.py   append-only, hash-chained call log + verify()
data/                 synthetic test data (read-only to the server)
skin/                 the app's skin template (see skin/README.md)
tests/test_server.py  server tests
tests/test_isolation.py  "cut off from all links" tests
TEST_RESULTS.txt      output of the last full run
REVIEW_FOR_MIKE.md    stricter readings chosen, conflicts, questions
```

## Run

```sh
python3 -m unittest discover -s tests -v                   # tests
python3 -m arbo_mcp --deploy-timeout 120                    # server on stdio
python3 -c "from arbo_mcp.calllog import verify; print(verify('logs/calls.jsonl'))"
```

## Roll back

`git log -- arbo-mcp` shows every change. `git checkout <commit> -- arbo-mcp`
returns this folder to any earlier state. `SHA256SUMS` fingerprints every
file in this release.
