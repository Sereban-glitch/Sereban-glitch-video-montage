# Режим Long (Длинные горизонтальные записи)

Пайплайн для монтажа судебных заседаний, лекций и конференций (1280×720 или 1920×1080) с последовательным рендером для защиты оперативной памяти (12 ГБ RAM).

---

## Главное правило: память

- **Никаких гигантских `filter_complex`**: рендер только отдельными ffmpeg-процессами для каждого интервала.
- Параметры: `-threads 2 -filter_threads 1`, `-preset veryfast`.
- В конце — склейка через `concat -c copy`.

---

## Порядок работы

```bash
PROJECT=~/projects/court-session
SKILL=~/.config/opencode/skills/video-montage

# 1. Извлечение 16кГц WAV и транскрипция (large-v3-turbo int8)
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/transcribe.py" --project "$PROJECT"

# 2. Аудит пауз (показывает тишину > 5с)
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/audit_gaps.py" --project "$PROJECT"

# 3. Чистка текста (Gemini 2.5 Flash или ручные text_fixes)
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/clean_transcript.py" --project "$PROJECT"

# 4. Построение плана монтажа и создание локальных ASS для каждого сегмента
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/build_edit.py" --project "$PROJECT"

# 5. Последовательный рендер сегментов и финальная склейка
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/render_segments.py" --project "$PROJECT"

# 6. Создание обложки 1280x720
"$PROJECT/.venv/bin/python" "$SKILL/scripts/long/make_thumbnail.py" --project "$PROJECT"

# 7. Загрузка в private и проверка
"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/upload_youtube.py" --project "$PROJECT"
"$PROJECT/.venv/bin/python" "$SKILL/scripts/publish/verify_upload.py" --project "$PROJECT"
```
