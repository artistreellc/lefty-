# Arbo MCP. For Mike: stricter choices, conflicts and questions

Nothing in this list is decided in code beyond what's described. Each item
says whether the stricter reading is for **safety**, **privacy** or **money**.

## A. Stricter readings I chose

1. **Only an explicit "yes" counts** (safety). The client must answer
   `accept` with the exact value `yes`. Decline, cancel, "YES", an empty
   accept, an error or garbage are all no.
2. **A client that can't ask Mike means no** (safety). The question isn't
   skipped, and the answer is recorded as no.
3. **No time limit on your decisions** (your ruling, Sep 26, 2026). The
   deploy question waits for as long as you take. Nothing happens while it
   waits, and silence never becomes a yes or a no. Other requests are
   answered meanwhile. A second deploy request waits its turn (safety: one
   decision at a time). A client that disconnects counts as no, and nothing
   happens.
4. **No log, no call** (safety). If the call log can't be written, the call
   is refused and nothing runs, including the deploy question.
5. **Strict arguments** (safety and privacy). Unknown arguments are refused.
   The read tools accept no file paths, so they can only read their two
   fixed files.
6. **This replaces two written rules; please confirm you meant both:**
   - the handoff's "a timeout counts as no" (and its test);
   - the brief's approval expiry (v2 D-3, 2.1: "unanswered approvals send
     nothing ... on expiry, the safe default applies, alert Mike").

   Nothing unsafe follows from removing them, because an unanswered item
   still sends and deploys nothing. The brief's expiry also alerted you and
   sent a holding text. **You said yes to a reminder instead (Sep 28, 2026),
   and it's built:** "Still waiting on you" goes out every 60 minutes
   (**your number to set**, `--remind-every-minutes`). It never decides,
   cancels or ends the wait (tested, including with planted bugs). A holding
   text to a customer isn't built; that would need your approval, like any
   send. When reminders reach a phone later, the aloft rule applies: nothing
   rings you while you're aloft.
   **Practical note:** some MCP clients give up on a tool call after their
   own wait. If one does, it disconnects, which is recorded as no, and
   nothing happens.
7. **The log is tamper-evident, not tamper-proof** (safety). It's
   hash-chained, so edits, deletions and reordering are detected (tested).
   The brief's database-enforced write-once log is later work.

## B. Needs your decision before the deploy tool ever does anything

8. **The "yes" doesn't prove it's you.** Anyone at the MCP client can answer
   the question, and there's no two-step check in this build. That's
   harmless now, because deploy deploys nothing. It must be solved before
   deploy does anything real (brief: approvals need a token from your own
   two-step session). Every answer is logged as "identity not verified."

## C. Where this was built (please read)

9. **This build ran in a Claude Code cloud session, not on a machine you
   control.** The code makes no network calls and nothing was installed.
   But the machine itself does have internet access through a proxy, so the
   handoff's "no internet access" is true of the code, not of the machine.
10. **Where it lives: decided by Mike.** *"Make sure it is in a sandbox on
    GitHub"* (Sep 26, 2026). It's in `artistreellc/lefty-` under `arbo-mcp/`.
    That replaces the handoff's rule 1 ("no git remote, no GitHub, ever").
    Note that **`lefty-` is a public repo**. This build holds only synthetic
    data and no keys, but anyone can read it.
11. **Other work in `lefty-`:** before this handoff, the same repo got a
    sandbox copy of your existing Arbo (`sandbox/`) and a shared Claude/Grok
    MCP server (`mcp/`). Those are separate from this build and were left
    untouched.

## D. Conflicts between the handoff and the brief (the brief wins; please confirm)

12. **Power-line distance as a fixed limit.** The handoff lists "the
    power-line distance" among the fixed limits nobody can override. The
    brief's fixed-limits table (2.0.1) has five limits (811, opt-outs, AI
    disclosure, 911 first, aloft hold), and power-line distance isn't one of
    them. The brief handles it as the assignment-guard rule N1 (2.3), which
    even your override of Jack's veto can't lift. Which is it?
13. **Storm Mode turning on by itself.** The handoff says plain code turns
    it on from official declarations. The brief (DB-32) says **auto-on stays
    off until Research confirms the declaration source is reliable**, and you
    switch it on yourself until then.
14. **The Claude halt session.** The handoff states it as settled. The brief
    marks it **PROPOSED, pending Jack's review**, and says it needs your
    explicit yes before anything is connected.
15. **"Resolved" decisions written by Grok Bot.** D-28, D-29, DB-32, DB-33,
    DB-35, DB-38, DB-40 and DB-41 are marked "safer default chosen by Grok
    Bot at caller's direction, as relayed from the 2:58 AM ET call." That's
    Grok's record of what you said. Please confirm those are your decisions.
16. **Authorization to build.** The brief says its approval "doesn't
    authorize building" and that each build needs your explicit yes. I took
    your message handing me this document as your yes for **this one build
    only** (the three-tool test server). Nothing else from the brief has been
    started.

## E. Links and the domain

18. **Cut off from all links.** Checked Sep 26, 2026:
    - Nothing in Arbo MCP points outside its own folder (tested).
    - No Vercel project is connected to the `lefty-` repo.
    - None of the four Railway projects deploys from it. Three were created
      today before this session and aren't Arbo MCP's:
      - `serene-encouragement`: a MySQL service, plus an environment named
        "Arbo grok ".
      - `abundant-joy`: the `tet` service, plus an environment named
        "Arbo 2.2".
      - `helpful-wholeness`: the `art-is-tree` service.

      **They were left untouched. Tell me if any of them should be removed.**
    - The repo itself is on GitHub (your decision, item 10). The Claude
      GitHub app used by this session can read and write it.
19. **Domain: nothing bought.** Every name checked was available on Sep 26,
    2026 (first-year price / renewal, from Vercel): `arbomcp.com`
    $11.25/$11.25, `arbomcp.app` $9.99/$15, `arbomcp.dev` $9.99/$13,
    `arbomcp.net` $13.50/$13.50, `arbomcp.io` $14.99/$46, `arbomcp.co`
    $29.99/$24.80, `arbomcp.ai` $160 for 2 years, and `arbo-mcp.com`,
    `arbo-mcp.app` and `getarbomcp.com` at the `.com`/`.app` prices. Buying
    one spends money and puts a public name on the project. The brief says
    Arbo isn't listed publicly (D-29). **Your call.**

## F. Not checked (outside this build)

20. I don't have *Arbo_Build_Brief_v2.md*, Jack's fact-checks or Research's
    files, so no legal citation, figure or vendor claim in the brief was
    checked. None of them are used by this build.

## G. Review checklist results (handoff rule 5)

| Check | Result |
|---|---|
| Network calls in the code | **0.** No network or process module is imported (tested), and the full server runs with the interpreter blocking network (tested). |
| Hard-coded web addresses | **0** in the code or data (tested). |
| Packages | **0.** Python standard library only. |
| Real credentials, names, addresses or phone numbers | **0.** All data is tagged `SIM` (tested). |
| Tests | **38 of 38 pass** (`TEST_RESULTS.txt`). Six planted bugs were each caught, which shows the tests can fail: a decline treated as yes, a skipped log entry, a read tool that writes, an outside font link in the skin, a reminder that ends the wait with "no", and a reminder clock that resets on every message. |
