#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    src = resolve(project, cfg["source"])
    wav = resolve(project, cfg["audio"])
    out = resolve(project, cfg["transcript"])
    wav.parent.mkdir(parents=True, exist_ok=True)

    if not wav.exists():
        print("extracting audio...", flush=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src),
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                str(wav),
            ],
            check=True,
        )

    with wave.open(str(wav), "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    print(f"audio samples={len(audio)} ({len(audio) / 16000:.1f}s)", flush=True)

    t0 = time.time()
    print("loading model...", flush=True)
    model = WhisperModel(
        cfg.get("whisper_model", "large-v3-turbo"),
        device="cpu",
        compute_type=cfg.get("whisper_compute", "int8"),
        cpu_threads=int(cfg.get("cpu_threads", 4)),
    )
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    language = cfg.get("language") or None
    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=int(cfg.get("beam_size", 5)),
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )
    print(
        f"language={info.language} prob={info.language_probability:.3f} "
        f"duration={info.duration:.1f}s",
        flush=True,
    )

    data = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": [],
    }
    for i, seg in enumerate(segments, 1):
        item = {
            "id": i,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": [
                {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                for w in (seg.words or [])
            ],
        }
        data["segments"].append(item)
        print(f"[{seg.start:7.1f}-{seg.end:7.1f}] {seg.text.strip()}", flush=True)

    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE segments={len(data['segments'])} elapsed={time.time() - t0:.1f}s -> {out}", flush=True)


if __name__ == "__main__":
    main()
