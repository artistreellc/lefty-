# Arbo MCP skin template

Every Arbo MCP screen starts from `template.html`. Copy the shell, keep the
components, and change only the content. Open `template.html` in any browser
to see it. It needs no connection.

| File | What it is |
|---|---|
| `tokens.css` | The only place colors, type, spacing and sizes are defined. Two themes: **cockpit** (dark, default) and **sunlight** (light, maximum contrast). |
| `skin.css` | The components, built only from the tokens. |
| `template.html` | Three real screens built from the skin, with SIMULATED data: **Owner Today** (instrument tiles, the queue of items waiting on you, the crew's day), **Owner Approval** (deploy request waiting with no time limit, safety-change card, text approval) and **Crew glove mode** (paused state, three-state aloft control, dig block, job flags, safety check). Wide screens show them side by side in phone frames. Phones show them full width. |

**Look (v2).** This is Arbo's approved cockpit direction:
- a near-black instrument panel with a faint grid and a violet glow;
- layered cards, HUD-style mono labels, and big mono numbers;
- one inline icon set (`<symbol>`s at the top of the template).

It's glove-friendly: nothing tappable is under 48px, and crew controls are
64px or more. It's readable in sunlight and usable one-handed, and it
respects the system's reduced-motion setting. The most important thing on a
screen is the biggest.

**Building a new screen:** copy one `.app` block from `template.html`, keep
the app bar and tab bar, and assemble the content from the existing parts
(`alert`, `tile`, `card`, `queue`, `timeline`, `waiting`, `segmented`,
`flags`, `chip`, `btn`). Put any ID in `<span class="id">` so it never
splits across lines.

## Rules every screen follows (checked by `tests/test_isolation.py`)

1. **Offline.** System fonts only. Nothing loads from outside this folder: no
   web fonts, CDNs, remote images, iframes, forms or network calls, and no
   browser storage.
2. **Nothing ever sits above the 911 banner.** When it's shown, it's first on the screen, it can't be dismissed, and it has the biggest button on the screen.
3. **Paused wording is word for word:** "Arbo paused, hand work allowed, fixed
   limits still apply (power-line distance, aloft rules), log it afterward."
4. **A dig block always reads "Can't confirm, don't dig."** Nothing on screen
   softens it.
5. **A dead feed is named** ("can't be confirmed"), never shown as zero or
   empty.
6. **Flags are listed, never counted.** There's no zero-flags or all-good
   state.
7. **Aloft has three states,** and Unknown is shown as "counts as aloft."
8. **Safety changes get their own card:** Jack's review first, and never a
   batch checkbox.
9. **No time limits on the owner's decisions** (owner's ruling, Sep 26, 2026). Screens
   never show a countdown or an expiry. A waiting decision says "No time
   limit. Nothing happens until you answer." Every approval card says what
   happens with no answer ("No answer sends nothing").
10. **Banned words never appear:** "clear," "healthy," "no disease found,"
    "no hazards," "someone will call you back," "Suffolk," "TCIA." VA811's
    own status words appear only after the label "VA811 status:".
11. **Synthetic only:** no real names, numbers or addresses.

## Changing the skin

Change the colors and sizes in `tokens.css` and nowhere else. A new component
goes into `skin.css` and gets an example in `template.html`.
