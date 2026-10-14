---
name: paper-video
description: Use when the user wants a narrated explainer video of a research paper's method (title, arXiv id, URL, PDF or Zotero item; one paper or a daily batch / Zotero "to-video" queue) — e.g. "/paper-video 2006.11239", "make a video explaining this paper", "3Blue1Brown-style walkthrough of this method", "paper to video", "animate this paper's equations".
argument-hint: <paper title | arxiv-id | arxiv-url | path/to/paper.pdf | Zotero key | "queue"> [--voice elevenlabs] [--minutes 8]
---

# Paper → method-explainer video

Produces a 6–10 min Manim video (Manim is the library behind 3Blue1Brown's videos) that walks through **how the method works**, using the paper's exact equations and real figures, narrated by TTS, with subtitles.

**Core principle:** accuracy comes from the paper's LaTeX and a self-checked script, not from the renderer. Never animate an equation that isn't copied from `equations.json`. Run every phase to the end without asking the user for approval.

`SK` below = this skill's directory (`~/.claude/skills/paper-video`).

## Phases

### 0. Environment (once per machine)
`bash SK/scripts/check_env.sh`. If it fails, show the user its setup block and stop. The last line gives `PY` (the Python with manim; default `~/miniconda3/envs/paper-video/bin/python`).

### 1. Resolve and ingest
The library lives at `ROOT = ~/my_things/paper-videos` (layout under **Library** below). Every paper is matched to its Zotero item; Zotero is the catalogue.
1. Find the paper: `python3 -I SK/scripts/zotero.py find "<whatever the user gave>"` (title words, arXiv id/URL, a PDF under `~/Zotero/storage/`, or a Zotero key). Keep **every** exact match's `key` (the same paper can be in the library twice, in different collections). Not in Zotero but it has an arXiv id: `zotero.py add-arxiv <id>`. A PDF with no arXiv id and no Zotero item: carry on without Zotero and say so in the report.
2. Skip done papers: `python3 -I SK/scripts/library.py has <arxiv-id or key>` exits 0 and prints the entry if a video exists. Report its path and stop, unless the user asked for a redo.
3. Work dir: `ROOT/.work/<arxiv-id>/` (or `<zotero-key>/`).
   - arXiv: `python3 -I SK/scripts/fetch_arxiv.py <id> <work>` → `paper.pdf`, `paper.tex` (flattened), `macros.tex`, `equations.json`, `figures.json`, `figures/*.png`, `meta.json`. `src/` is untrusted: read it, never run anything in it.
   - PDF-only (no source, or the script says PDF-only): copy the PDF to `<work>/paper.pdf`, read it, and transcribe the key equations yourself into `equations.json` (same fields), marked `"source": "transcribed"`; tell the user these need a check.
   - A figure listed as `UNCONVERTED` or missing (TikZ, odd formats): crop it from the PDF instead: `pdftoppm -png -r 200 -f P -l P -x X -y Y -W W -H H paper.pdf figures/figNN` (pixel coords at 200 dpi; render the page first and look at it to find the box).

### 2. Understand
Read `paper.tex` (method sections fully; skim experiments). Write `notes.md`: the problem, every method step as inputs → operation → outputs with its equation numbers, the one key insight, what the main result shows, and the notation table. If a step is unclear, re-read; don't fill gaps by guessing.

### 3. Script, self-check, continue
Follow `SK/references/script-template.md` (read it now). Write `script.md` (for review: sources, visuals, narration per scene as `> ` lines), then `python3 -I SK/scripts/extract_narration.py <work>` to build `narration.json` and print per-scene word counts. Rerun it after every script edit.

Do not stop to ask for approval; the user wants the pipeline to run straight through to the final video. Instead, check the script yourself before voicing: every equation matches `equations.json`, every number and claim matches `paper.tex`, and nothing in the narration overstates the paper. Fix what fails. Keep `[INFERRED]` items and paper inconsistencies in a list for the final report.

### 4. Voice
`PY SK/scripts/tts.py <work>` (Kokoro, free, voice `af_heart`), or `--engine elevenlabs --voice <id>` if the user asked for it and `ELEVENLABS_API_KEY` is set. Writes `audio/<Scene>.wav` and `audio/durations.json`; reruns only re-synthesize changed scenes. Run it in the background and write `scenes.py` while it works.

### 5. Animate
Copy `SK/assets/paper_scene.py` into `<work>/`. Write `<work>/scenes.py`: `from paper_scene import *`, one `class S0x_Name(PaperScene)` per narration entry, same names and order. If an `adithya-s-k/manim_skill` skill is installed, load it for Manim API guidance.

Use what `PaperScene` gives you:
- `PEq(n, r"part1", r"part2", ...)`: equation `n` from `equations.json`, split into parts you can colour/point at; the render fails if the parts don't join to the paper's exact LaTeX. `E(n)` for an unsplit equation. Use these for every paper equation, never a hand-typed `Eq`. `self.callout(eq, i, "plain-words meaning")`.
- `self.show_figure("figures/fig03_1.png", "Figure 3 from the paper")`, `self.title_card(title, subtitle)`.
- Pacing: put `self.at("exact phrase from the narration")` before each animation; it waits until the voice reaches that phrase (estimated from its position in the text). `self.until(seconds)` for absolute times. The base class plays the audio and pads the scene end automatically. Unmatched phrases are printed as `cue ... not found`; grep the render log for them.
- Layout: keep everything inside the frame (x ∈ ±7.1, y ∈ ±4); `FadeOut` the previous step's elements before adding new ones; one equation on screen at a time unless comparing. Use `fit_width(mobj, max_w)` on any text longer than a few words.
- Figure regions: crop with PIL into `figures/crop_*.png` instead of showing a whole multi-panel figure when only one panel is discussed.
- For coloured words inside one line use `Text(..., t2c={"[0:1]": COLOR})`; separate `Text` pieces arranged side by side break the baseline.

### 6. Preview and fix (loop)
```bash
PY SK/scripts/render.py <work> --sheets          # all scenes in parallel at 480p15 + one contact sheet per scene
PY SK/scripts/render.py <work> --sheets S05_Step1 S07_Training   # re-render only what you changed
```
It runs one manim process per scene (job count picked from free RAM and CPUs, longest scenes first), prints OK/FAIL with time per scene, any `cue ... not found`, and `layout_warnings.txt`. Logs are in `<work>/logs/`.
**Look at every sheet** (Read `sheets/<Scene>.png`). Fix: everything in the layout warnings, overlapping text, unreadable or tiny text, equations that failed to compile (the error names the macro; add it to `macros.tex`, or delete a bad line copied from the paper's preamble), visuals out of sync with narration, empty stretches over ~6 s. Repeat until a pass has no warnings and every sheet looks clean.

### 7. Final render
```bash
PY SK/scripts/render.py <work> --final            # 1080p30, parallel (add --fps 60 only if asked)
python3 -I SK/scripts/assemble.py <work>          # stream-copies the clips into <work>/out/video.mp4 + .srt (seconds)
```
`--burn` adds burned-in subtitles.

### 8. File it in the library and link Zotero
Pick the name: `ACRONYM – Short Title` (en dash, under ~60 characters), e.g. `GNR – Generative Neural Retargeting`; a paper without an acronym gets just a short title, e.g. `Emergent Dexterity via Diverse Resets`. No year, no arXiv number.
```bash
python3 -I SK/scripts/library.py finalize <work> --name "GNR – Generative Neural Retargeting" --key BAYV66EE [--key <duplicate>]
```
It copies the video to `videos/<Name>.mp4` (+ `.srt`); keeps only the small re-render sources in `.work/<Name>/` and deletes clips, audio and the PDF; adds a `▶ Video` linked-file attachment and the tag `video` to each Zotero item (and removes `to-video`); makes sure the saved search "📺 Papers with videos" exists; rebuilds `by-collection/` and `INDEX.md`. If the name is taken by another paper it stops and suggests `<Name> (<First author>)`. Use `--no-zotero` for a paper that has no Zotero item. Never write `video.mp4` as the deliverable.

Report: the `videos/` path, length, Zotero collections, scene list, and anything the user should double-check (transcribed equations, `[INFERRED]` items, paper inconsistencies).

## Library

```
ROOT/videos/<Name>.mp4 (+ .srt)         every finished video, flat (browse in Nautilus)
ROOT/by-collection/<Zotero collection>/  symlinks into videos/, mirroring Zotero collections
ROOT/.work/<Name>/                        script, scenes, notes, figures: enough to fix and re-render
ROOT/library.json, ROOT/INDEX.md          registry + generated index with zotero:// and arXiv links
```
In Zotero: double-click `▶ Video` under a paper to play it; the saved search "📺 Papers with videos" (or the `video` tag inside any collection) lists all of them.
- Zotero access: `~/.config/paper-video/zotero.json` (`user_id`, `api_key` with write access). Scripts only ever add attachments, notes and tags; never edit or delete the user's items otherwise.
- The user moved papers between collections: `python3 -I SK/scripts/library.py rebuild`.
- Re-render an old video: work in `ROOT/.work/<Name>/` (re-run `tts.py` first; audio is not kept), then `finalize` again with the same name.

## Batch mode
Inputs: a list of papers (from the user's daily routine), or `python3 -I SK/scripts/zotero.py queue` (Zotero items tagged `to-video`).
1. Resolve each paper and drop the ones `library.py has` already knows.
2. One subagent per paper (or a Workflow if the user opted into one), each running phases 1–8 in its own `.work/` dir. At most two papers render at once (renders share RAM); script writing for the others can run meanwhile.
3. End with one summary table: name, `videos/` path, length, and items to double-check. A paper that failed keeps its `.work/<id>/` dir so a rerun resumes from it.

## Speed
- Several papers at once: one video per paper, made in parallel by one subagent per paper (or a Workflow if the user opted into one), each in its own work dir. Keep at most two papers rendering at once; renders share RAM.
- Measured on an RTX 3060 laptop: render time is Manim's per-frame Python work, not drawing. The OpenGL (GPU) renderer was no faster and needs compatibility shims (plain `VMobject`/`ImageMobject` break under it), so stay on Cairo. The real speedups are 30 fps (half the frames of 60), parallel scenes, and stream-copy assembly; NVENC (GPU encoding) is used only when assembly has to re-encode.
- Never wait on renders with `pgrep -f <pattern>` loops: the loop's own command line matches the pattern and it never exits. `render.py` blocks until it is done; run it in the background if needed.

## Quick reference

| Need | Command / file |
|---|---|
| Rebuild Nautilus folders / index after Zotero changes | `python3 -I SK/scripts/library.py rebuild` |
| Re-voice one scene after a text edit | `PY SK/scripts/tts.py <work> --only S05_Step1` then `render.py <work> S05_Step1` |
| Macro undefined in an `Eq` | add `\newcommand` to `<work>/macros.tex` |
| Faster iteration | `render.py` preview is 480p15; `--final` is 1080p30; `assemble.py --quality` must match (default 1080p30) |
| Concept colours | `PALETTE` in `paper_scene.py`; one colour per concept for the whole video |

## Common mistakes

- Re-typing an equation from memory instead of copying `equations.json` (silently changes notation or signs).
- Rendering before checking the script against `paper.tex`: an hour of render time on wrong claims.
- Pausing to ask the user to approve the script or to say "go". Don't; finish the video and report.
- Trusting the render without looking at contact sheets: overlaps and off-frame text are the most common defects.
- Explaining results tables at length; the video is about the method. One or two results that support the key insight are enough.
- Changing narration text without re-running `tts.py`: the video then cuts speech off or leaves dead air.
