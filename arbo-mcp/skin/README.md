# Arbo MCP skin template

Every Arbo MCP screen starts from `template.html`. Copy the shell, keep the
components, and change only the content. Open `template.html` in any browser
to see it. It needs no connection.

| File | What it is |
|---|---|
| `tokens.css` | The only place colors, type, spacing and sizes are defined. Two themes: **cockpit** (dark, default) and **sunlight** (light, maximum contrast). |
| `skin.css` | The components, built only from the tokens. |
| `template.html` | The app shell plus every component, filled with SIMULATED data. |

**Look.** This is Arbo's approved cockpit palette: near-black base, violet
accent, mono numbers. It's glove-friendly (nothing tappable under 48px),
readable in sunlight, and usable one-handed. The most important thing on a
screen is the biggest.

## Rules every screen follows (checked by `tests/test_isolation.py`)

1. **Offline.** System fonts only. Nothing loads from outside this folder: no
   web fonts, CDNs, remote images, iframes, forms or network calls, and no
   browser storage.
2. **The 911 banner is always first** and can't be dismissed.
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
9. **Every approval card says what happens with no answer** ("No answer sends
   nothing," "counts as no").
10. **Banned words never appear:** "clear," "healthy," "no disease found,"
    "no hazards," "someone will call you back," "Suffolk," "TCIA." VA811's
    own status words appear only after the label "VA811 status:".
11. **Synthetic only:** no real names, numbers or addresses.

## Changing the skin

Change the colors and sizes in `tokens.css` and nowhere else. A new component
goes into `skin.css` and gets an example in `template.html`.
