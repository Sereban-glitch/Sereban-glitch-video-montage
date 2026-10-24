#!/usr/bin/env python3
import argparse
import json
import wave
from pathlib import Path

import numpy as np


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    ap.add_argument("--transcribe", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    data = json.loads(resolve(project, cfg["transcript"]).read_text(encoding="utf-8"))

    min_gap = float(cfg.get("audit_min_gap", 5.0))
    duration = float(data["duration"])
    gaps = []
    prev_end = 0.0
    for seg in data["segments"]:
        if seg["start"] - prev_end >= min_gap:
            gaps.append((prev_end, seg["start"]))
        prev_end = max(prev_end, seg["end"])
    if duration - prev_end >= min_gap:
        gaps.append((prev_end, duration))

    print("GAPS:", flush=True)
    for a, b in gaps:
        print(f"  {a:7.1f}-{b:7.1f}  {b - a:7.1f}s", flush=True)

    if not args.transcribe or not gaps:
        return

    from faster_whisper import WhisperModel

    with wave.open(str(resolve(project, cfg["audio"])), "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    model = WhisperModel(
        cfg.get("audit_model", "small"),
        device="cpu",
        compute_type="int8",
        cpu_threads=int(cfg.get("cpu_threads", 4)),
    )
    for a, b in gaps:
        print(f"=== GAP {a:.1f}-{b:.1f} ===", flush=True)
        chunk = audio[int(a * 16000):int(b * 16000)]
        segments, _ = model.transcribe(
            chunk,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        for seg in segments:
            text = seg.text.strip()
            if text:
                print(f"{a + seg.start:7.1f}-{a + seg.end:7.1f} {text}", flush=True)


if __name__ == "__main__":
    main()
