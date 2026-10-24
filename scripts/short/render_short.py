#!/usr/bin/env python3
"""Renders a vertical Short (1080x1920) with trimmed cuts, burned ASS subtitles, top title & label, and normalized audio."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Add common utils to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from common.utils import ass_time, wrap_text_pixel, run_cmd


def build_ass(
    edits,
    captions,
    ass_path: Path,
    label_text: str = "",
    title_text: str = "",
    sub_font_size: int = 50,
    sub_max_w: int = 960,
    font_dir: str = "/usr/share/fonts/truetype/dejavu"
) -> float:
    duration = sum(b - a for a, b in edits)

    def local_time(t: float) -> float:
        offset = 0.0
        for a, b in edits:
            if a <= t <= b:
                return offset + (t - a)
            offset += b - a
        raise ValueError(f"Time {t} outside specified edit ranges")

    rows = []
    for start, end, text in captions:
        if not any(a <= start < b for a, b in edits):
            continue
        try:
            a = local_time(start)
            z = local_time(end)
            if z > a:
                rows.append((a, z, text))
        except ValueError:
            continue

    def style(name, size, bold, border_style, outline, shadow, align, mv, back):
        return (
            f"Style: {name},DejaVu Sans,{size},&H00FFFFFF,&H000000FF,&H00101010,{back},"
            f"{bold},0,0,0,100,100,0,0,{border_style},{outline},{shadow},{align},40,40,{mv},1"
        )

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style("Label", 28, 1, 1, 2, 0, 8, 55, "&H00000000")}
{style("Title", 58, 1, 3, 10, 0, 8, 125, "&H99000000")}
{style("Sub", sub_font_size, 1, 3, 8, 0, 2, 250, "&HAA000000")}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = ""
    if label_text:
        body += f"Dialogue: 0,{ass_time(0)},{ass_time(duration)},Label,,0,0,0,,{{\\fad(200,0)}}{label_text}\n"
    if title_text:
        body += f"Dialogue: 0,{ass_time(0)},{ass_time(duration)},Title,,0,0,0,,{{\\fad(200,0)}}{title_text}\n"

    for a, z, text in rows:
        formatted = wrap_text_pixel(text, size=sub_font_size, max_width=sub_max_w)
        body += (
            f"Dialogue: 0,{ass_time(a)},{ass_time(z)},Sub,,0,0,0,,"
            f"{{\\fad(80,60)}}{formatted}\n"
        )

    ass_path.write_text(header + body, encoding="utf-8")
    return duration


def render_short(
    src_video: Path,
    out_video: Path,
    ass_path: Path,
    edits,
    duration: float,
    font_dir: str = "/usr/share/fonts/truetype/dejavu"
) -> None:
    parts = []
    for i, (a, b) in enumerate(edits):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")

    concat_in = "".join(f"[v{i}][a{i}]" for i in range(len(edits)))
    parts.append(f"{concat_in}concat=n={len(edits)}:v=1:a=1[vc][ac]")
    parts.append(
        f"[vc]scale=1080:1920:flags=lanczos,unsharp=3:3:0.35:3:3:0.0,"
        f"subtitles={ass_path.as_posix()}:fontsdir={font_dir}[v]"
    )
    parts.append(
        f"[ac]loudnorm=I=-14:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=0.15,afade=t=out:st={max(0, duration - 0.35):.3f}:d=0.35[a]"
    )

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-y",
        "-filter_threads", "1", "-i", str(src_video),
        "-filter_complex", ";".join(parts),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", "-threads", "2",
        str(out_video),
    ]
    run_cmd(cmd)


def main():
    ap = argparse.ArgumentParser(description="Render a vertical YouTube Short with subtitles")
    ap.add_argument("--project", default=".", help="Project directory")
    ap.add_argument("--config", default="short.json", help="Config file name or path")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_file = Path(args.config)
    cfg_path = cfg_file if cfg_file.is_absolute() else project / cfg_file

    if not cfg_path.exists():
        # Fallback to config.json
        cfg_path = project / "config.json"
        if not cfg_path.exists():
            sys.exit(f"Error: configuration file not found at {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    src = project / cfg.get("source", "source/input.mp4")
    out = project / cfg.get("output", "final.mp4")
    ass = project / cfg.get("ass_path", "subtitles.ass")

    edits = [tuple(x) for x in cfg.get("edits", [])]
    captions = [tuple(x) for x in cfg.get("captions", [])]
    overlay = cfg.get("overlay", {})

    label = overlay.get("label", "")
    title = overlay.get("title", "")
    if isinstance(title, list):
        title = "\\N".join(title)

    sub_font_size = cfg.get("subtitle_size", 50)
    sub_max_w = cfg.get("subtitle_max_width", 960)

    duration = build_ass(
        edits=edits,
        captions=captions,
        ass_path=ass,
        label_text=label,
        title_text=title,
        sub_font_size=sub_font_size,
        sub_max_w=sub_max_w
    )

    print(f"[Short] ASS generated: duration={duration:.2f}s, captions={len(captions)}", flush=True)
    render_short(src, out, ass, edits, duration)
    print(f"[Short] Finished rendering: {out} ({out.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
