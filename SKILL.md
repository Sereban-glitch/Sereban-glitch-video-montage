---
name: video-montage
description: Use when нужно смонтировать вертикальный Short (YouTube Shorts, Telegram, 1080x1920) или длинное судебное заседание/лекцию (1280x720) с субтитрами, нарезкой пауз, обложкой и загрузкой на YouTube в private. Триггеры: монтаж видео, шорт, short, вертикальное видео, судебное заседание, судове засідання, субтитры, YouTube, court-montage, нарезка пауз, «сделай видео», «смонтируй шорт».
metadata:
  opencode/slash: "true"
---

# Video Montage v2 — монтажная кухня

Универсальный пайплайн для двух типов задач:
1. **Short (вертикальные ролики)**: 1080×1920, 30 fps, верхний титул, динамические субтитры (2–3 строки с пиксельным контролем), вертикальная обложка.
2. **Long (длинные записи/заседания)**: 1280×720 / 1920×1080, умный аудит пауз, последовательный рендер сегментов (защита 12 ГБ RAM), обложка, главы.

---

## Главное правило безопасности: память

На этом ПК 12 ГБ ОЗУ.
- **Для длинных видео**: **не рендерить всё одним `filter_complex`** — рендер только отдельными процессами через `scripts/long/render_segments.py`, затем склейка `concat -c copy`.
- **Для Shorts (до 3 минут)**: допустим однопроходный рендер через `scripts/short/render_short.py` с ограничением `-threads 2 -filter_threads 1`.

---

## Режим 1: Short (вертикальные видео 1080×1920)

### 1. Подготовка
Создай папку проекта (например `~/projects/my-short`), положи исходник в `source/input.mp4`.
Скопируй шаблоны:
```bash
SKILL=~/.config/opencode/skills/video-montage
cp "$SKILL/templates/short.config.example.json" short.json
cp "$SKILL/templates/thumbnail.short.example.json" thumbnail.json
```

### 2. Рендер видео и обложки
```bash
python3 "$SKILL/scripts/short/render_short.py" --project . --config short.json
python3 "$SKILL/scripts/short/thumb_short.py" --project . --config thumbnail.json
```

### 3. Загрузка в private
```bash
.venv/bin/python "$SKILL/scripts/publish/upload_youtube.py" --project .
.venv/bin/python "$SKILL/scripts/publish/verify_upload.py" --project .
```

---

## Режим 2: Long (длинные записи судов / лекций)

### 1. Подготовка
```bash
PROJECT=~/projects/my-long-video
SKILL=~/.config/opencode/skills/video-montage

mkdir -p "$PROJECT/source"
cp /path/to/input.mp4 "$PROJECT/source/input.mp4"
cp "$SKILL/templates/long.config.example.json" "$PROJECT/config.json"
cp "$SKILL/templates/metadata.example.json" "$PROJECT/metadata.json"
cp "$SKILL/templates/thumbnail.long.example.json" "$PROJECT/thumbnail.json"
```

### 2. Шаги пайплайна
1. **Транскрипция**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/transcribe.py" --project "$PROJECT"`
2. **Аудит пауз**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/audit_gaps.py" --project "$PROJECT"`
3. **Чистка текста**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/clean_transcript.py" --project "$PROJECT"`
4. **План монтажа и сегменты**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/build_edit.py" --project "$PROJECT"`
5. **Последовательный рендер**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/render_segments.py" --project "$PROJECT"`
6. **Обложка 1280x720**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/make_thumbnail.py" --project "$PROJECT"`
7. **Загрузка и проверка**:
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/upload_youtube.py" --project "$PROJECT"`
   `"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/verify_upload.py" --project "$PROJECT"`

---

## Профили каналов (`profiles/`)

Профили хранятся в папке `profiles/` (например `profiles/humanrightszp.json`). Они задают ID канала, дефолтные стили субтитров и обложек, но **не содержат секретов**. Токен OAuth подключается локально в проекте или через `~/.config/youtube/`.
