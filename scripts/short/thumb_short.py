#!/usr/bin/env python3
"""Generates a high-impact vertical (1080x1920) YouTube Shorts thumbnail."""

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
except ImportError:
    sys.exit("Error: Pillow is required. Run 'pip install Pillow'.")

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT_REG = FONT_DIR / "DejaVuSans.ttf"

W, H = 1080, 1920
YELLOW = (247, 206, 70)
INK = (15, 17, 20)
WHITE = (255, 255, 255)


def get_font(path, size):
    return ImageFont.truetype(str(path), size)


def fit_font(path, text, max_width, start_size):
    size = start_size
    while size > 20:
        f = get_font(path, size)
        box = f.getbbox(text)
        if box[2] - box[0] <= max_width:
            return f
        size -= 2
    return get_font(path, size)


def center_text(draw, y, text, f, fill, stroke=0, stroke_fill=INK):
    box = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
    x = (W - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    return box[3] - box[1]


def make_gradient(width, height, top_alpha, bottom_alpha):
    img = Image.new("L", (1, height))
    px = img.load()
    for y in range(height):
        t = y / max(1, height - 1)
        px[0, y] = int(255 * (top_alpha + (bottom_alpha - top_alpha) * t))
    return img.resize((width, height))


def create_thumbnail(
    bg_path: Path,
    out_path: Path,
    label: str = "",
    title_lines: list = None,
    subline: str = "",
    pill_text: str = "",
    author_name: str = "",
    handle: str = "",
    zoom: float = 1.25,
    focus_y: float = 0.47
):
    if not bg_path.exists():
        sys.exit(f"Error: Base image not found at {bg_path}")

    src = Image.open(bg_path).convert("RGB")
    cw, ch = int(src.width / zoom), int(src.height / zoom)
    cx, cy = src.width // 2, int(src.height * focus_y)
    left, top = cx - cw // 2, cy - ch // 2
    img = src.crop((left, top, left + cw, top + ch)).resize((W, H), Image.LANCZOS)

    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.07)
    img = ImageEnhance.Color(img).enhance(1.04)
    img = ImageEnhance.Sharpness(img).enhance(1.18)

    # Top gradient for title readability
    top_grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    top_grad.putalpha(make_gradient(W, H, 0.72, 0.0))
    img = Image.alpha_composite(img.convert("RGBA"), top_grad)

    # Bottom gradient for pill / handle readability
    bot_grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bot_grad.putalpha(make_gradient(W, H, 0.0, 0.68))
    img = Image.alpha_composite(img, bot_grad)

    d = ImageDraw.Draw(img)

    if label:
        label_f = get_font(FONT_BOLD, 34)
        center_text(d, 82, label, label_f, YELLOW)

    if title_lines:
        longest = max(title_lines, key=len)
        title_f = fit_font(FONT_BOLD, longest, 960, 94)
        y = 148
        for line in title_lines:
            h = center_text(d, y, line, title_f, WHITE, stroke=7)
            y += h + 18

        d.rectangle([(W - 220) // 2, y + 8, (W + 220) // 2, y + 16], fill=YELLOW)

        if subline:
            sub_f = get_font(FONT_BOLD, 38)
            center_text(d, y + 40, subline, sub_f, WHITE)

    if pill_text:
        pill_f = fit_font(FONT_BOLD, pill_text, 700, 58)
        pb = d.textbbox((0, 0), pill_text, font=pill_f)
        pw = pb[2] - pb[0] + 88
        ph = 100
        px = (W - pw) // 2
        py = 1510
        d.rounded_rectangle([px, py, px + pw, py + ph], radius=18, fill=YELLOW)
        tb = d.textbbox((0, 0), pill_text, font=pill_f)
        d.text(
            ((W - (tb[2] - tb[0])) // 2, py + (ph - (tb[3] - tb[1])) // 2 - tb[1]),
            pill_text,
            font=pill_f,
            fill=INK,
        )

    if author_name:
        name_f = get_font(FONT_BOLD, 34)
        center_text(d, 1698, author_name, name_f, WHITE)

    if handle:
        handle_f = get_font(FONT_BOLD, 30)
        center_text(d, 1782, handle, handle_f, WHITE)

    img.convert("RGB").save(out_path, quality=94, subsampling=0)
    print(f"[Thumbnail] Created {out_path} ({out_path.stat().st_size} bytes)")


def main():
    ap = argparse.ArgumentParser(description="Generate vertical 1080x1920 YouTube Short thumbnail")
    ap.add_argument("--project", default=".", help="Project directory")
    ap.add_argument("--config", default="thumbnail.short.json", help="Thumbnail config json")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = project / args.config
    if not cfg_path.exists():
        cfg_path = project / "thumbnail.json"
        if not cfg_path.exists():
            sys.exit(f"Config not found: {cfg_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    bg = project / cfg.get("background", "thumb_base.png")
    out = project / cfg.get("output", "thumbnail.jpg")

    create_thumbnail(
        bg_path=bg,
        out_path=out,
        label=cfg.get("label", ""),
        title_lines=cfg.get("title_lines", []),
        subline=cfg.get("subline", ""),
        pill_text=cfg.get("pill_text", ""),
        author_name=cfg.get("author_name", ""),
        handle=cfg.get("handle", ""),
        zoom=cfg.get("zoom", 1.25),
        focus_y=cfg.get("focus_y", 0.47)
    )


if __name__ == "__main__":
    main()
