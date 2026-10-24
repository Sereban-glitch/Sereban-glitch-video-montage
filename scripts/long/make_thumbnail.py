#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "thumbnail.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    W, H = 1280, 720
    base = Image.open(resolve(project, cfg.get("background", "thumb_base.jpg"))).convert("RGB")
    base = base.resize((W, H), Image.LANCZOS)
    base = ImageEnhance.Contrast(base).enhance(float(cfg.get("contrast", 1.06)))
    base = ImageEnhance.Color(base).enhance(float(cfg.get("saturation", 1.08)))

    grad = Image.new("L", (W, H), 0)
    px = grad.load()
    start = int(cfg.get("gradient_start", 520))
    for x in range(W):
        a = 0 if x < start else int(min(215, (x - start) * 0.62))
        for y in range(H):
            px[x, y] = a
    base = Image.composite(Image.new("RGB", (W, H), (8, 10, 14)), base, grad)

    bottom = Image.new("L", (W, H), 0)
    bp = bottom.load()
    for y in range(H):
        a = 0 if y < 470 else int(min(170, (y - 470) * 0.7))
        for x in range(W):
            bp[x, y] = a
    base = Image.composite(Image.new("RGB", (W, H), (5, 6, 9)), base, bottom)

    d = ImageDraw.Draw(base)
    bold_path = cfg.get("font_bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    reg_path = cfg.get("font_regular", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

    def font(path, size):
        return ImageFont.truetype(path, size)

    d.rectangle([0, 0, 10, 360], fill=(0, 87, 183))
    d.rectangle([0, 360, 10, 720], fill=(255, 215, 0))

    label = cfg.get("label", "СУДОВЕ ЗАСІДАННЯ")
    label_size = int(cfg.get("label_size", 34))
    d.text((665, 92), label, font=font(bold_path, label_size), fill=(255, 215, 0))

    lines = cfg.get("title_lines", ["ЗАГОЛОВОК"])
    size = int(cfg.get("title_size", 50))
    accent_index = int(cfg.get("accent_index", len(lines) - 1))
    max_width = 600
    while size > 24:
        f = font(bold_path, size)
        widest = max(d.textbbox((0, 0), line, font=f)[2] for line in lines)
        if widest <= max_width:
            break
        size -= 2

    y = 160
    step = size + 16
    for i, line in enumerate(lines):
        color = (255, 215, 0) if i == accent_index else (255, 255, 255)
        d.text((662, y), line, font=font(bold_path, size), fill=color)
        y += step

    d.rectangle([665, y + 12, 1235, y + 17], fill=(255, 215, 0))
    d.text((665, y + 36), cfg.get("subtitle", ""), font=font(reg_path, 25), fill=(235, 238, 242))
    d.text((665, y + 76), cfg.get("subline", ""), font=font(reg_path, 22), fill=(178, 186, 196))

    channel = cfg.get("channel", "")
    d.text((42, 660), channel, font=font(bold_path, 23), fill=(255, 255, 255))

    avatar_path = cfg.get("avatar", "")
    if avatar_path and resolve(project, avatar_path).exists():
        av = Image.open(resolve(project, avatar_path)).convert("RGB")
        size_av = 104
        av = av.resize((size_av, size_av), Image.LANCZOS)
        mask = Image.new("L", (size_av * 4, size_av * 4), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size_av * 4 - 1, size_av * 4 - 1), fill=255)
        mask = mask.resize((size_av, size_av), Image.LANCZOS)
        base.paste(av, (1136, 584), mask)
        d.ellipse([1133, 581, 1243, 691], outline=(255, 215, 0), width=3)

    out = resolve(project, cfg.get("output", "thumbnail.jpg"))
    base.save(out, quality=93, subsampling=0)
    print(f"THUMBNAIL {out} {base.size}", flush=True)


if __name__ == "__main__":
    main()
