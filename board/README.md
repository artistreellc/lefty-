# Shared board

Written by the `lefty-arbo` MCP server (`board_*` tools). Do not hand-edit
while a server is running.

- `tasks.json`: tasks. Statuses are `open`, `in_progress`, `review`,
  `needs_mike` and `done`. Only Mike sets `done`.
- `handoffs.jsonl`: one handoff message per line, newest last.

Committed to git, so every change to the board is reviewable in a PR.
