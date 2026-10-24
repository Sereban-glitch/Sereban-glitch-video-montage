#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return -1.0
    try:
        return float(r.stdout.strip())
    except ValueError:
        return -1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    segs = json.loads((project / "segments.json").read_text(encoding="utf-8"))
    src = resolve(project, cfg["source"])
    outdir = project / "segs"
    final = project / "final.mp4"

    if not args.resume:
        shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(exist_ok=True)
    if final.exists() and not args.resume:
        final.unlink()

    render = cfg.get("render", {})
    threads = int(render.get("threads", 2))
    preset = render.get("preset", "veryfast")
    crf = int(render.get("crf", 21))
    abitrate = render.get("audio_bitrate", "160k")
    arate = int(render.get("audio_rate", 48000))
    achannels = int(render.get("audio_channels", 2))
    nice = shutil.which("nice")
    ionice = shutil.which("ionice")

    for i, iv in enumerate(segs):
        dur = iv["end"] - iv["start"]
        out = outdir / f"seg_{i}.mp4"
        if args.resume and out.exists() and abs(probe_duration(out) - dur) < 0.5:
            print(f"[{time.strftime('%H:%M:%S')}] skip {i} (resume)", flush=True)
            continue

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-ss", f"{iv['start']:.3f}", "-t", f"{dur:.3f}",
            "-i", str(src),
            "-map", "0:v:0", "-map", "0:a:0",
            "-vf", f"subtitles={project / 'seg_ass' / f'seg_{i}.ass'}:fontsdir=/usr/share/fonts/truetype/dejavu",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", "30",
            "-x264-params", f"threads={threads}:lookahead_threads=1",
            "-threads", str(threads), "-filter_threads", "1",
            "-c:a", "aac", "-b:a", abitrate, "-ar", str(arate), "-ac", str(achannels),
            "-movflags", "+faststart", str(out),
        ]
        if ionice:
            cmd = ["ionice", "-c", "2", "-n", "7"] + cmd
        if nice:
            cmd = [nice, "-n", "10"] + cmd

        print(
            f"[{time.strftime('%H:%M:%S')}] segment {i}: "
            f"{iv['start']:.3f}-{iv['end']:.3f} ({dur:.1f}s)",
            flush=True,
        )
        t0 = time.time()
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"FAILED segment {i} rc={r.returncode}", flush=True)
            sys.exit(1)
        print(f"[{time.strftime('%H:%M:%S')}] done {i} in {time.time() - t0:.0f}s", flush=True)

    concat = outdir / "concat.txt"
    with open(concat, "w", encoding="utf-8") as f:
        for i in range(len(segs)):
            f.write(f"file '{outdir / f'seg_{i}.mp4'}'\n")

    print(f"[{time.strftime('%H:%M:%S')}] concatenating", flush=True)
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c", "copy", "-movflags", "+faststart", str(final),
        ]
    )
    if r.returncode != 0:
        print(f"CONCAT FAILED rc={r.returncode}", flush=True)
        sys.exit(1)

    print(
        f"[{time.strftime('%H:%M:%S')}] ALL DONE "
        f"duration={probe_duration(final):.2f}s -> {final}",
        flush=True,
    )


if __name__ == "__main__":
    main()
