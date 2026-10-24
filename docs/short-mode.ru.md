# Режим Short (Короткие вертикальные видео)

Пайплайн для нарезки динамичных вертикальных видео YouTube Shorts (1080×1920, 30 fps) с верхним постоянным титулом, субтитрами с автоподгонкой и яркой обложкой.

---

## Концепция

- **Разрешение:** 1080×1920 (вертикаль, 9:16).
- **Длительность:** до 3 минут (YouTube Shorts).
- **Стили титров:**
  - `Label`: жёлтый текст 28px, маргин 55px (например, `КСУ • 29.09.2026`).
  - `Title`: белый текст 58px в 2 строки на полупрозрачной подложке, маргин 125px (например, `УРЯД НЕ МОЖЕ\nСАМ ОБМЕЖУВАТИ ПРАВА`).
  - `Sub`: субтитры 50px, полупрозрачный фон, маргин снизу 250px (чтобы не перекрываться элементами интерфейса Shorts).
- **Звук:** нормализация EBU R128 (`loudnorm=I=-14:TP=-1.5:LRA=11`).

---

## Запуск одной командой

```bash
PROJECT=~/projects/my-short
SKILL=~/.config/opencode/skills/video-montage

# 1. Рендер видео
"$PROJECT/.venv/bin/python" "$SKILL/scripts/short/render_short.py" --project "$PROJECT" --config short.json

# 2. Генерация вертикальной обложки
"$PROJECT/.venv/bin/python" "$SKILL/scripts/short/thumb_short.py" --project "$PROJECT" --config thumbnail.json

# 3. Загрузка в private
"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/upload_youtube.py" --project "$PROJECT"

# 4. Проверка статуса
"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/verify_upload.py" --project "$PROJECT"
```
