#!/usr/bin/env python3
"""Shared utilities for video montage (Short and Long pipelines)."""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    from PIL import ImageFont
except ImportError:
    ImageFont = None

DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ass_time(t: float) -> str:
    """Format seconds into ASS timestamp h:mm:ss.cc"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def get_font(font_path: str = DEFAULT_FONT, size: int = 50):
    if ImageFont is None:
        raise RuntimeError("Pillow is required for pixel-based font measurements")
    return ImageFont.truetype(font_path, size)


def wrap_text_pixel(
    text: str,
    font_path: str = DEFAULT_FONT,
    size: int = 50,
    max_width: int = 960
) -> str:
    """Wraps text into 1, 2, or 3 lines using PIL pixel-based bounding box."""
    font = get_font(font_path, size)

    def text_w(s: str) -> int:
        return font.getbbox(s)[2]

    if text_w(text) <= max_width:
        return text

    words = text.split()
    # Try 2 lines
    best_two = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(text_w(a), text_w(b))
        if score <= max_width and (best_two is None or score < best_two[0]):
            best_two = (score, [a, b])
    if best_two:
        return "\\N".join(best_two[1])

    # Try 3 lines
    best_three = None
    for i in range(1, len(words) - 1):
        for j in range(i + 1, len(words)):
            lines = [" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:])]
            score = max(text_w(x) for x in lines)
            if score <= max_width and (best_three is None or score < best_three[0]):
                best_three = (score, lines)
    if best_three:
        return "\\N".join(best_three[1])

    return text


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run shell command with warning loglevel and error checking."""
    return subprocess.run(cmd, check=check)


def get_media_info(filepath: Path) -> Dict[str, Any]:
    """Retrieve media information via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", str(filepath)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)
