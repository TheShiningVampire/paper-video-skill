#!/usr/bin/env python3
"""Concatenate rendered scenes into one MP4 with subtitles.

Usage: python assemble.py <work-dir> [--quality 1080p30] [--name Paper_Name] [--burn]

Reads narration.json for scene order and text, finds media/videos/scenes/<quality>/<Scene>.mp4,
writes <work-dir>/out/video.mp4 (soft subtitles), out/video.srt, and with --burn out/video_subs.mp4.
--name also copies them to out/<name>.mp4 / .srt (name videos after the paper).
Stream-copies when all scene clips match (the normal case); otherwise re-encodes with
NVIDIA NVENC when ffmpeg has it, else libx264. --burn also uses NVENC when available.
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def video_codec():
    """GPU (NVENC) H.264 when available and working, else CPU libx264."""
    test = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                           "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    if test.returncode == 0:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
    return ["-c:v", "libx264", "-crf", "18"]


def stream_sig(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,sample_rate,channels",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return out.stdout


def chunks(text, limit=84):
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        words, line = sent.split(), ""
        for w in words:
            if len(line) + len(w) + 1 > limit and line:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        if line:
            out.append(line)
    return out


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--quality", default="1080p30", help="manim output dir: 480p15, 1080p30, 1080p60")
    ap.add_argument("--name", help="also save out/<name>.mp4/.srt, e.g. the paper's (short) title")
    ap.add_argument("--burn", action="store_true", help="also write a copy with burned-in subtitles")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    scenes = json.loads((work / "narration.json").read_text())
    durs = json.loads((work / "audio" / "durations.json").read_text())
    vdir = work / "media" / "videos" / "scenes" / a.quality
    missing = [s["scene"] for s in scenes if not (vdir / f"{s['scene']}.mp4").exists()]
    if missing:
        sys.exit(f"Missing renders in {vdir}: {', '.join(missing)}")
    out = work / "out"
    out.mkdir(exist_ok=True)

    srt, n, offset = [], 1, 0.0
    for s in scenes:
        clip = vdir / f"{s['scene']}.mp4"
        speech = durs.get(s["scene"], probe(clip))
        parts = chunks(s["text"])
        total_chars = sum(len(p) for p in parts) or 1
        t = offset
        for p in parts:
            d = speech * len(p) / total_chars
            srt.append(f"{n}\n{ts(t)} --> {ts(t + d)}\n{p}\n")
            n, t = n + 1, t + d
        offset += probe(clip)
    (out / "video.srt").write_text("\n".join(srt))

    lst = out / "concat.txt"
    lst.write_text("".join(f"file '{vdir / (s['scene'] + '.mp4')}'\n" for s in scenes))
    clips = [vdir / f"{s['scene']}.mp4" for s in scenes]
    # Manim writes every scene with identical stream settings, so concatenation can copy the
    # streams (seconds) instead of re-encoding (about a minute); re-encode only if they differ.
    same = len({stream_sig(c) for c in clips}) == 1
    codec = ["-c:v", "copy", "-c:a", "copy"] if same else \
        [*video_codec(), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-i", str(out / "video.srt"), "-map", "0:v", "-map", "0:a?", "-map", "1",
                    *codec, "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
                    str(out / "video.mp4")], check=True)
    if a.burn:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "video.mp4"),
                        "-vf", f"subtitles={out / 'video.srt'}:force_style='FontSize=18,MarginV=24'",
                        *video_codec(), "-c:a", "copy", str(out / "video_subs.mp4")], check=True)
    final = out / "video.mp4"
    if a.name:
        name = re.sub(r"[^\w.-]+", "_", a.name).strip("_")
        shutil.copyfile(out / "video.mp4", out / f"{name}.mp4")
        shutil.copyfile(out / "video.srt", out / f"{name}.srt")
        final = out / f"{name}.mp4"
    print(f"{final}  ({probe(final) / 60:.1f} min, {len(scenes)} scenes)")


if __name__ == "__main__":
    main()
