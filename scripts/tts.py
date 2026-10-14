#!/usr/bin/env python3
"""Synthesize one narration audio file per scene and record durations.

Usage: python tts.py <work-dir> [--engine kokoro|elevenlabs] [--voice NAME] [--only SCENE ...]

Reads  <work-dir>/narration.json : [{"scene": "S01_Hook", "text": "..."}, ...]
Writes <work-dir>/audio/<scene>.wav and <work-dir>/audio/durations.json {scene: seconds}
Scenes whose text is unchanged since the last run are skipped (hash in durations.json).
"""
import argparse, hashlib, json, os, subprocess, sys, urllib.request
from pathlib import Path


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def kokoro_engine(voice):
    import numpy as np, soundfile as sf
    from kokoro import KPipeline
    pipe = KPipeline(lang_code=voice[0])  # 'a' American, 'b' British, ...

    def synth(text, wav):
        chunks = [a for _, _, a in pipe(text, voice=voice, speed=1.0)]
        sf.write(wav, np.concatenate(chunks), 24000)
    return synth


def elevenlabs_engine(voice):
    key = os.environ.get("ELEVENLABS_API_KEY") or sys.exit("ELEVENLABS_API_KEY is not set")

    def synth(text, wav):
        req = urllib.request.Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
            data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode(),
            headers={"xi-api-key": key, "Content-Type": "application/json"})
        mp3 = Path(wav).with_suffix(".mp3")
        with urllib.request.urlopen(req, timeout=300) as r:
            mp3.write_bytes(r.read())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), str(wav)], check=True)
        mp3.unlink()
    return synth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--engine", default="kokoro", choices=["kokoro", "elevenlabs"])
    ap.add_argument("--voice", help="kokoro voice (default af_heart) or ElevenLabs voice id")
    ap.add_argument("--only", nargs="*", help="re-synthesize just these scenes")
    a = ap.parse_args()
    work = Path(a.work)
    scenes = json.loads((work / "narration.json").read_text())
    audio = work / "audio"
    audio.mkdir(exist_ok=True)
    dfile = audio / "durations.json"
    durs = json.loads(dfile.read_text()) if dfile.exists() else {}
    hashes = durs.pop("_hash", {})
    voice = a.voice or ("af_heart" if a.engine == "kokoro" else "JBFqnCBsd6RMkjVDRZzb")
    synth = None
    for s in scenes:
        name, text = s["scene"], s["text"].strip()
        h = hashlib.sha1(f"{a.engine}|{voice}|{text}".encode()).hexdigest()[:12]
        wav = audio / f"{name}.wav"
        if wav.exists() and hashes.get(name) == h and not (a.only and name in a.only):
            continue
        if a.only and name not in a.only:
            continue
        synth = synth or (kokoro_engine if a.engine == "kokoro" else elevenlabs_engine)(voice)
        synth(text, str(wav))
        durs[name], hashes[name] = round(duration(wav), 3), h
        print(f"{name}: {durs[name]:.1f}s")
    durs["_hash"] = hashes
    dfile.write_text(json.dumps(durs, indent=2))
    total = sum(v for k, v in durs.items() if k != "_hash")
    print(f"total narration: {total / 60:.1f} min")


if __name__ == "__main__":
    main()
