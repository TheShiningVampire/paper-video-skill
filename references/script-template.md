# Method-explainer script template (7–9 min, ~1,100–1,350 spoken words)

Narration speed is about 150 words/min. Scene names become Manim class names and audio file names.
Fill `script.md` (for the human review) and `narration.json` (spoken text only) from this.

| Scene | Purpose | Time | Words | Visual |
|---|---|---|---|---|
| S01_Hook | The concrete problem, shown, not described. Why existing approaches fall short, in one example. | 0:00–0:40 | ~100 | A toy input + the failure of the naive approach |
| S02_Promise | One sentence: "By the end you'll know how X does Y, and why step Z is the key idea." Name the paper once. | 0:40–1:00 | ~50 | Title card (title, authors, year) |
| S03_Setup | Notation and the toy example used for the rest of the video. Define every symbol before it is used. | 1:00–2:00 | ~150 | Symbol table built up one row at a time |
| S04_Overview | The whole pipeline in one picture: inputs → stages → output. Use the paper's own overview figure if it has one. | 2:00–2:45 | ~110 | Paper figure, or a Manim block diagram |
| S05_Step1 … S0k_StepN | One scene per method step: what goes in, what comes out, the equation, each term in plain words, the toy example run through it. | 2:45–6:45 | ~150 each | Equation built term by term, callouts, toy numbers flowing through |
| S0x_KeyInsight | The one idea that makes it work. Contrast with the obvious alternative and show why that fails. | ~1:00 | ~140 | Side by side: naive vs. method |
| S0x_Training | Loss / objective, training loop, inference loop if different. Pseudo-code if the paper has an algorithm box. | ~0:50 | ~120 | Algorithm box revealed line by line |
| S0x_Evidence | The 1–2 results that support the key insight (not every table). Say what is compared to what. | ~0:40 | ~90 | Cropped result figure/table, highlight the relevant cell |
| S0x_Limits | What it does not do, assumptions, costs. | ~0:25 | ~60 | Bullet list |
| S0x_Recap | Rebuild the pipeline picture from S04 with every stage now named; restate the key insight. | ~0:30 | ~70 | Overview diagram, stages lighting up in order |

## Rules for the script

- Every equation shown must be copied from `equations.json` (paper's LaTeX). Cite it in `script.md` as `Eq. n` with its label.
- Every claim about results cites the figure/table it comes from.
- Introduce a symbol in words before it appears on screen; never show more than one new equation per ~20 s.
- Keep one running toy example (tiny sizes: 3 tokens, 2D points, a 4×4 image) through all method scenes.
- Each concept keeps one colour for the whole video (list the mapping at the top of `script.md`).
- Write for the ear: short sentences, no "as shown in Table 3", no citations read aloud, spell out symbols ("x sub t").
- Mark anything you inferred rather than read in the paper with `[INFERRED]` so the reviewer checks it.

## script.md layout per scene

```
## S05_Step1 — Forward noising  (≈1:00, 148 words)
Source: Sec 2, Eq. 2 (eq:forward), Eq. 4
Visual: Eq 2 written left to right; callouts on β_t and sqrt(1-β_t); toy 2D point drifting to noise over 5 steps.
Narration:
> ...spoken text...
```

## narration.json

Generated from the `> ` lines of `script.md` by `scripts/extract_narration.py`; don't hand-edit it.

```json
[
  {"scene": "S01_Hook", "text": "Spoken text only. No markdown, no LaTeX."},
  {"scene": "S02_Promise", "text": "..."}
]
```
