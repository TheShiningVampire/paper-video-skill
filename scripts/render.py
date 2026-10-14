#!/usr/bin/env python3
"""Render all (or some) scenes of a paper video in parallel, one manim process per scene.

Usage: PY render.py <work-dir> [--final] [--fps 30] [--jobs N] [--sheets] [Scene ...]

  default   preview: -ql (480p15), writes media/videos/scenes/480p15/
  --final   1080p at --fps (default 30): writes media/videos/scenes/1080p<fps>/
  --sheets  after rendering, write one contact sheet per scene to sheets/<Scene>.png
  --jobs    parallel manim processes; default picks from free RAM and CPU count

Manim's per-frame cost is Python-bound (Cairo or OpenGL alike), so speed comes from
fewer frames (30 fps) and running scenes side by side, not from the GPU.
Logs: <work>/logs/<quality>_<Scene>.log. Exit code 1 if any scene failed.
"""
import argparse, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MEM_PER_JOB_GB = {"preview": 0.5, "final": 1.0}


def avail_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return 4.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--sheets", action="store_true")
    a = ap.parse_intermixed_args()

    work = Path(a.work).resolve()
    src = (work / "scenes.py").read_text()
    scenes = a.scenes or re.findall(r"^class (S\w+)\(", src, flags=re.M)
    durs = {}
    if (work / "audio" / "durations.json").exists():
        durs = {k: v for k, v in json.loads((work / "audio" / "durations.json").read_text()).items()
                if isinstance(v, (int, float))}
    scenes.sort(key=lambda s: -durs.get(s, 0))  # longest first packs the pool better

    mode = "final" if a.final else "preview"
    qflags = ["-qh", "--frame_rate", str(a.fps)] if a.final else ["-ql"]
    quality = f"1080p{a.fps}" if a.final else "480p15"
    jobs = a.jobs or max(1, min((os.cpu_count() or 2) - 1, int(avail_gb() / MEM_PER_JOB_GB[mode]), len(scenes)))
    logs = work / "logs"
    logs.mkdir(exist_ok=True)
    warn = work / "layout_warnings.txt"
    if warn.exists():  # drop stale warnings for the scenes being re-rendered
        keep = [l for l in warn.read_text().splitlines(True) if l.split(":")[0] not in scenes]
        warn.write_text("".join(keep))
    print(f"[render] {len(scenes)} scenes, {quality}, {jobs} parallel jobs", flush=True)

    def run(scene):
        t = time.time()
        log = logs / f"{quality}_{scene}.log"
        # own LaTeX dir per process: parallel manims sharing media/Tex race on the same .tex files
        cfg = logs / f"{scene}.cfg"
        cfg.write_text(f"[CLI]\ntex_dir = {work / 'media' / 'Tex' / scene}\n")
        with open(log, "w") as f:
            r = subprocess.run([sys.executable, "-m", "manim", "-c", str(cfg), *qflags, "--disable_caching",
                                "scenes.py", scene], cwd=work, stdout=f, stderr=subprocess.STDOUT)
        return scene, r.returncode, time.time() - t, log

    t0, failed = time.time(), []
    with ThreadPoolExecutor(jobs) as ex:
        for fut in as_completed([ex.submit(run, s) for s in scenes]):
            scene, rc, dt, log = fut.result()
            text = log.read_text(errors="replace")
            cues = re.findall(r"cue .*? not found in \w+", text)
            status = "OK  " if rc == 0 else "FAIL"
            print(f"  {status} {scene:24s} {dt:6.1f}s" + (f"  ({len(cues)} cues not found)" if cues else ""),
                  flush=True)
            for c in cues:
                print(f"       {c}")
            if rc:
                failed.append(scene)
    for scene in list(failed):  # one sequential retry rules out transient parallel failures
        scene, rc, dt, log = run(scene)
        print(f"  {'OK  ' if rc == 0 else 'FAIL'} {scene:24s} {dt:6.1f}s  (retry)", flush=True)
        if rc == 0:
            failed.remove(scene)
        else:
            err = [l for l in log.read_text(errors="replace").splitlines() if re.search(r"Error|error:", l)]
            print("       " + "\n       ".join(err[-3:] or ["see " + str(log)]))
    print(f"[render] done in {time.time() - t0:.0f}s; output media/videos/scenes/{quality}/")

    if warn.exists() and warn.read_text().strip():
        print("[render] layout warnings:\n" + warn.read_text())

    if a.sheets:
        sheets = work / "sheets"
        sheets.mkdir(exist_ok=True)
        for s in scenes:
            v = work / "media" / "videos" / "scenes" / quality / f"{s}.mp4"
            if v.exists():
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(v), "-vf",
                                "fps=1/4,scale=480:-1,tile=4x4", "-frames:v", "1", str(sheets / f"{s}.png")])
        print(f"[render] contact sheets in {sheets}/")

    if failed:
        print(f"[render] FAILED: {' '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
