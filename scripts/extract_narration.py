#!/usr/bin/env python3
"""Build narration.json from script.md: each '## S0x_Name: ...' scene's '> ' lines are its spoken text.

Usage: python3 -I extract_narration.py <work-dir>
"""
import json, re, sys
from pathlib import Path

work = Path(sys.argv[1])
out = []
for block in re.split(r"^## ", (work / "script.md").read_text(), flags=re.M)[1:]:
    lines = [l[2:].strip() for l in block.splitlines() if l.startswith("> ")]
    if lines:
        out.append({"scene": re.split(r"[:\s]", block, maxsplit=1)[0], "text": " ".join(lines)})
(work / "narration.json").write_text(json.dumps(out, indent=1))
total = 0
for o in out:
    w = len(o["text"].split())
    total += w
    print(f"{o['scene']:20s} {w:4d} words  ~{w / 2.5:4.0f}s")
print(f"total {total} words  ~{total / 150:.1f} min")
