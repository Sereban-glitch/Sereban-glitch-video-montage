# Скрипты video-montage

Все скрипты запускаются из любого места и принимают `--project <папка>`.
Конфиг по умолчанию — `<project>/config.json`.

| Скрипт | Что делает |
|---|---|
| `setup_venv.sh <project>` | создаёт `.venv`, ставит faster-whisper, YouTube API, Pillow, numpy |
| `transcribe.py` | извлекает WAV, транскрибирует Whisper, пишет `transcript.json` |
| `audit_gaps.py` | показывает паузы > `audit_min_gap`; с `--transcribe` проверяет их моделью `small` |
| `clean_transcript.py` | чистит текст через Gemini-прокси, пишет `transcript_clean.json` |
| `build_edit.py` | строит интервалы, ASS/SRT, `seg_ass/`, `segments.json` |
| `render_segments.py` | последовательно рендерит сегменты и склеивает `final.mp4`; `--resume` |
| `make_thumbnail.py` | собирает обложку 1280x720 по `thumbnail.json` |
| `auth_youtube.py` | OAuth один раз, сохраняет `token.json` (chmod 600) |
| `upload_youtube.py` | проверяет канал, грузит `final.mp4` private, ставит обложку |

Пример:

```bash
SKILL=~/.config/opencode/skills/video-montage
PROJECT=~/projects/my-video
bash "$SKILL/scripts/setup_venv.sh" "$PROJECT"
"$PROJECT/.venv/bin/python" "$SKILL/scripts/transcribe.py" --project "$PROJECT"
"$PROJECT/.venv/bin/python" "$SKILL/scripts/build_edit.py" --project "$PROJECT"
"$PROJECT/.venv/bin/python" "$SKILL/scripts/render_segments.py" --project "$PROJECT"
```

Зависимости: `ffmpeg`, `ffprobe`, Python 3.10+, интернет для первой загрузки модели.
