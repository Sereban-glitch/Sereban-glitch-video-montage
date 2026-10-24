#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


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

    clean = resolve(project, cfg["clean_transcript"])
    raw = resolve(project, cfg["transcript"])
    data = json.loads((clean if clean.exists() else raw).read_text(encoding="utf-8"))

    markers = cfg.get("artifact_markers", ["Дякую за перегляд"])
    segs = [s for s in data["segments"] if not any(m in s["text"] for m in markers)]
    if not segs:
        raise SystemExit("no speech segments")

    duration = float(data["duration"])
    max_gap = float(cfg.get("max_gap", 3.0))
    pad = float(cfg.get("pad", 0.6))

    blocks = []
    cur = None
    for s in segs:
        if cur is None:
            cur = {"start": s["start"], "end": s["end"], "ids": [s["id"]]}
        elif s["start"] - cur["end"] <= max_gap:
            cur["end"] = max(cur["end"], s["end"])
            cur["ids"].append(s["id"])
        else:
            blocks.append(cur)
            cur = {"start": s["start"], "end": s["end"], "ids": [s["id"]]}
    if cur:
        blocks.append(cur)

    intervals = []
    for b in blocks:
        a = max(0.0, b["start"] - pad)
        z = min(duration, b["end"] + pad)
        intervals.append({"start": round(a, 3), "end": round(z, 3), "ids": b["ids"]})

    offset = 0.0
    for iv in intervals:
        iv["out_start"] = round(offset, 3)
        offset += iv["end"] - iv["start"]
        iv["out_end"] = round(offset, 3)

    plan = {"duration": duration, "output_duration": round(offset, 3), "intervals": intervals}
    (project / "edit_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    def map_time(t):
        for iv in intervals:
            if iv["start"] <= t <= iv["end"]:
                return iv["out_start"] + (t - iv["start"])
        return None

    sub = cfg.get("subtitle", {})
    max_chars = int(sub.get("max_chars", 84))
    max_line = int(sub.get("max_line_chars", 44))

    def split_text(text, limit=max_chars):
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return [text]
        parts = re.split(r"(?<=[.!?;:])\s+", text)
        out = []
        for p in parts:
            if len(p) <= limit:
                out.append(p)
            else:
                line = ""
                for w in p.split():
                    if len(line) + len(w) + 1 > limit and line:
                        out.append(line)
                        line = w
                    else:
                        line = (line + " " + w).strip()
                if line:
                    out.append(line)
        return out

    def wrap2(text, width=max_line):
        words = text.split()
        lines, line = [], ""
        for w in words:
            if len(line) + len(w) + 1 > width and line:
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            lines.append(line)
        if len(lines) > 2:
            lines = [lines[0], " ".join(lines[1:])]
        return "\\N".join(lines)

    def ass_time(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def srt_time(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    events = []
    for s in segs:
        a, z = s["start"], s["end"]
        out_a, out_z = map_time(a), map_time(z)
        if out_a is None or out_z is None or out_z <= out_a:
            continue
        chunks = split_text(s["text"])
        total_chars = sum(len(c) for c in chunks) or 1
        t = a
        for c in chunks:
            d = max(1.2, min(7.0, (z - a) * len(c) / total_chars))
            e = min(z, t + d)
            oa, oz = map_time(t), map_time(e)
            if oa is not None and oz is not None and oz > oa:
                events.append({"start": oa, "end": oz, "text": c})
            t = e

    font = sub.get("font", "DejaVu Sans")
    size = int(sub.get("size", 34))
    margin_l = int(sub.get("margin_l", 60))
    margin_r = int(sub.get("margin_r", 60))
    margin_v = int(sub.get("margin_v", 36))
    outline = float(sub.get("outline", 2.2))
    shadow = float(sub.get("shadow", 0.8))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    ass = header
    for e in events:
        ass += f"Dialogue: 0,{ass_time(e['start'])},{ass_time(e['end'])},Default,,0,0,0,,{wrap2(e['text'])}\n"
    (project / "subtitles.ass").write_text(ass, encoding="utf-8")

    with open(project / "subtitles.srt", "w", encoding="utf-8") as f:
        for i, e in enumerate(events, 1):
            f.write(f"{i}\n{srt_time(e['start'])} --> {srt_time(e['end'])}\n{e['text']}\n\n")

    segdir = project / "seg_ass"
    segdir.mkdir(exist_ok=True)
    for old in segdir.glob("seg_*.ass"):
        old.unlink()

    with open(project / "segments.txt", "w", encoding="utf-8") as f:
        for i, iv in enumerate(intervals):
            body = ""
            for e in events:
                if e["start"] >= iv["out_start"] - 1e-6 and e["end"] <= iv["out_end"] + 1e-6:
                    body += (
                        f"Dialogue: 0,{ass_time(e['start'] - iv['out_start'])},"
                        f"{ass_time(e['end'] - iv['out_start'])},Default,,0,0,0,,{wrap2(e['text'])}\n"
                    )
            (segdir / f"seg_{i}.ass").write_text(header + body, encoding="utf-8")
            f.write(f"file 'seg_{i}.mp4'\nduration {iv['end'] - iv['start']:.6f}\n")

    (project / "segments.json").write_text(
        json.dumps(intervals, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(
        f"blocks={len(intervals)} output={plan['output_duration'] / 60:.2f}min "
        f"events={len(events)} cut={duration - plan['output_duration']:.1f}s",
        flush=True,
    )
    for i, iv in enumerate(intervals):
        print(
            f"  {i:2d} {iv['start']:7.1f}-{iv['end']:7.1f} "
            f"-> {iv['out_start']:7.1f}-{iv['out_end']:7.1f} "
            f"({iv['end'] - iv['start']:6.1f}s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
