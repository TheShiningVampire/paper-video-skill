#!/usr/bin/env python3
"""File a finished paper video into the library and link it to Zotero.

Library root (default ~/my_things/paper-videos):
  videos/<Name>.mp4 (+ .srt)              every finished video, flat
  by-collection/<Zotero collection>/...   symlinks into videos/, rebuilt from Zotero each run
  .work/<Name>/                           small text sources kept for a re-render (script, scenes, notes, figures)
  library.json                            registry (one entry per video), INDEX.md generated from it

  library.py finalize <work> --name "GNR – Generative Neural Retargeting" [--key ZKEY ...] [--no-zotero]
      --key: Zotero item key(s); default = look up meta.json's arXiv id (added to Zotero if missing)
  library.py rebuild          refresh collections from Zotero, rebuild by-collection/ and INDEX.md
  library.py has <arxiv-id|zotero-key>   exit 0 and print the entry if a video already exists
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zotero  # noqa: E402

ROOT = Path(os.environ.get("PAPER_VIDEOS_ROOT", Path.home() / "my_things/paper-videos"))
KEEP = {"script.md", "notes.md", "scenes.py", "paper_scene.py", "narration.json", "equations.json",
        "figures.json", "macros.tex", "meta.json", "paper.tex", "figures"}


def reg_path():
    return ROOT / "library.json"


def load():
    p = reg_path()
    return json.loads(p.read_text()) if p.exists() else []


def save(reg):
    reg_path().write_text(json.dumps(reg, indent=1, ensure_ascii=False))


def safe(name):
    return re.sub(r'[/\\:*?"<>|]', "-", name).strip()


def duration(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                         capture_output=True, text=True).stdout.strip()
    return float(out) if out else 0.0


def find_video(work):
    out = Path(work) / "out"
    if (out / "video.mp4").exists():
        return out / "video.mp4"
    mp4s = sorted(out.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not mp4s:
        raise SystemExit(f"no video in {out}")
    return mp4s[-1]


def finalize(work, name, keys, use_zotero=True):
    work = Path(work).resolve()
    meta = json.loads((work / "meta.json").read_text()) if (work / "meta.json").exists() else {}
    arxiv = meta.get("arxiv_id") or meta.get("id") or (re.search(r"\d{4}\.\d{4,5}", work.name) or [None])[0]
    name = safe(name)
    src = find_video(work)
    if duration(src) <= 0:
        raise SystemExit(f"{src} is not a playable video (interrupted assembly?)")

    items = []
    if use_zotero:
        if keys:
            items = [zotero.summarize(zotero.api("GET", f"/items/{k}")) for k in keys]
        elif arxiv:
            items = [r for r in zotero.find(arxiv) if r["arxiv"] == arxiv] or [zotero.add_arxiv(arxiv)]
    reg = load()
    ids = {i["key"] for i in items} | ({arxiv} if arxiv else set())
    clash = [e for e in reg if e["name"] == name and not (ids & ({e.get("arxiv")} | set(e["zotero_keys"])))]
    if clash:
        first = (items[0]["authors"][0] if items and items[0]["authors"] else "2")
        raise SystemExit(f'name "{name}" is taken by another paper; use "{name} ({first})"')

    vids = ROOT / "videos"
    vids.mkdir(parents=True, exist_ok=True)
    dst = vids / f"{name}.mp4"
    shutil.copy2(src, dst)
    srt = src.with_suffix(".srt")
    if srt.exists():
        shutil.copy2(srt, dst.with_suffix(".srt"))

    # keep only small re-render sources under .work/<name>
    keep_dir = ROOT / ".work" / name
    if keep_dir.resolve() != work:
        if keep_dir.exists():
            shutil.rmtree(keep_dir)
        keep_dir.mkdir(parents=True)
        for f in work.iterdir():
            if f.name in KEEP:
                shutil.move(str(f), keep_dir / f.name)
        shutil.rmtree(work)
    else:
        for f in list(work.iterdir()):
            if f.name not in KEEP:
                shutil.rmtree(f) if f.is_dir() else f.unlink()

    linked = [zotero.link(i["key"], dst) for i in items] if use_zotero else []
    if use_zotero:
        zotero.ensure_search()
    entry = {
        "name": name, "file": f"videos/{dst.name}", "arxiv": arxiv,
        "title": (items[0]["title"] if items else meta.get("title", name)),
        "authors": (items[0]["authors"] if items else meta.get("authors", [])),
        "zotero_keys": [i["key"] for i in items],
        "collections": sorted({c for i in items for c in i["collections"]}),
        "minutes": round(duration(dst) / 60, 1), "made": datetime.date.today().isoformat(),
        "work": f".work/{name}",
    }
    reg = [e for e in reg if not (ids & ({e.get("arxiv")} | set(e["zotero_keys"]))) and e["name"] != name] + [entry]
    save(reg)
    build(reg)
    return entry | {"zotero_links": linked}


def refresh(reg):
    cols = zotero.collection_paths()
    for e in reg:
        got = []
        for k in e["zotero_keys"]:
            try:
                got += zotero.summarize(zotero.api("GET", f"/items/{k}"), cols)["collections"]
            except Exception as ex:  # item deleted in Zotero: keep old collections
                print(f"warning: {e['name']}: {k}: {ex}", file=sys.stderr)
                got += e["collections"]
        e["collections"] = sorted(set(got))
    save(reg)
    return reg


def build(reg):
    bc = ROOT / "by-collection"
    if bc.exists():
        shutil.rmtree(bc)
    for e in reg:
        for c in e["collections"] or ["_Not in a collection"]:
            d = bc / safe_path(c)
            d.mkdir(parents=True, exist_ok=True)
            link = d / Path(e["file"]).name
            link.symlink_to(os.path.relpath(ROOT / e["file"], d))
    rows = sorted(reg, key=lambda e: e["made"], reverse=True)
    lines = ["# Paper videos", "",
             f"{len(reg)} videos. Open a paper in Zotero with its link; in Zotero, the saved search "
             f"\"{zotero.SEARCH_NAME}\" or the tag `video` lists them all.", "",
             "| Video | Paper | Authors | Min | Collections | Made | Links |", "|---|---|---|---|---|---|---|"]
    for e in rows:
        au = ", ".join(e["authors"][:3]) + (" et al." if len(e["authors"]) > 3 else "")
        links = " ".join(f"[Zotero](zotero://select/library/items/{k})" for k in e["zotero_keys"])
        if e.get("arxiv"):
            links += f" [arXiv](https://arxiv.org/abs/{e['arxiv']})"
        vid = f"[{e['name']}](<{e['file']}>)"
        lines.append(f"| {vid} | {e['title']} | {au} | {e['minutes']} | {'; '.join(e['collections'])} "
                     f"| {e['made']} | {links} |")
    (ROOT / "INDEX.md").write_text("\n".join(lines) + "\n")


def safe_path(c):
    return Path(*[safe(p) for p in c.split("/")])


def has(ident):
    for e in load():
        if ident == e.get("arxiv") or ident in e["zotero_keys"]:
            print(json.dumps(e, indent=1, ensure_ascii=False))
            return 0
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("finalize")
    f.add_argument("work")
    f.add_argument("--name", required=True)
    f.add_argument("--key", action="append", default=[])
    f.add_argument("--no-zotero", action="store_true")
    sub.add_parser("rebuild")
    h = sub.add_parser("has")
    h.add_argument("ident")
    a = ap.parse_args()
    if a.cmd == "finalize":
        print(json.dumps(finalize(a.work, a.name, a.key, not a.no_zotero), indent=1, ensure_ascii=False))
    elif a.cmd == "rebuild":
        build(refresh(load()))
        print(f"rebuilt {len(load())} entries")
    else:
        sys.exit(has(a.ident))
