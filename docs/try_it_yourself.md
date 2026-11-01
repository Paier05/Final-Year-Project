# Try the harness prompt by hand

These are the **exact** prompts the harness sends — not simplified versions. Paste
them into any chat UI (ChatGPT, Claude, Gemini, an Ollama/vLLM box, a different
Qwen endpoint) to see how a model behaves on ARC-AGI-3 without running the sweep.

**How to use:** paste `system_prompt.txt` as the system message (or just as the
first message if the UI has no system field), then paste one scenario file as the
user message. A correct reply is a single JSON object and nothing else.

| File | What it tests |
|---|---|
| `system_prompt.txt` | the harness rules; always send this first |
| `try_ls20_step1.txt` | **cold start.** One action taken, almost no evidence. Tests whether the model explores systematically or guesses. |
| `try_ls20_step12.txt` | **dynamics inference.** 12 actions of evidence, with a textbook object-translation diff. Tests whether it reads the diff properly. |
| `try_vc33_click.txt` | **click targeting.** Only ACTION6 is available, so it must produce valid `{"x","y"}` coordinates and pick a sensible target. |

## What a good answer looks like

```json
{"thought": "ACTION1/ACTION3 move the bands up, ACTION2/ACTION4 move them down. The blue+black pixels near (32,21) are the likely target.",
 "action": "ACTION1",
 "args": {},
 "scratchpad": "ACTION1 = up ~5 rows. ACTION2 = down. Target: blue(1)+black(0) cluster at rows31-33,cols20-22. Bands currently rows45-49."}
```

## What to look for

These are the failure modes the experiment is trying to measure, and you can spot
all of them by hand:

1. **Does it emit clean JSON?** Anything before or after the object is a parse
   failure in the real harness. Qwen3.8-27B with thinking *on* writes paragraphs
   of prose first and nearly blows the token limit — that is exactly why the
   committed config sets `thinking: "off"`.
2. **Does it read the diff, or just the object list?** In `try_ls20_step12.txt`
   the diff shows 15 cells leaving maroon and 15 arriving, 10 leaving teal and 10
   arriving, all within `cols29-38`. That balanced pattern is a **rigid object
   moving**, not a recolour. A model that says "the colours changed" has missed it.
3. **Does it notice the repetition trap?** In `try_ls20_step12.txt` the history
   shows ACTION1-4 cycled three times, each reporting "52 cells changed". A good
   answer stops cycling and starts using what it learned. A weak one keeps probing.
4. **Click sanity (`try_vc33_click.txt`).** `x` is the **column**, `y` is the
   **row**, both `0..63`. Models routinely swap them. Note the game is giving tiny
   1-2 cell diffs at `(0,59)` — top-right corner, far from the interesting objects.
5. **Is the scratchpad useful?** It is the only memory past 10 steps. Notes like
   "I tried ACTION1" are wasted; "ACTION1 = up ~5 rows" is what pays off later.

## Comparing models

Send the same three scenarios to different models and compare. The cheapest
useful signal is scenario 2: whether the model works out that
**ACTION1/ACTION3 move one way and ACTION2/ACTION4 the other** purely from the
diff. That single inference is most of what separates a model that can play these
games from one that wanders for 200 actions.
