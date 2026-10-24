# Инструкция по восстановлению (Restore Guide)

Если компьютер сломался или переустановлена система — по этой инструкции навык и вся среда разворачиваются за 3 минуты.

---

## 1. Системные зависимости

На чистом Linux (Linux Mint, Ubuntu, Debian):

```bash
sudo apt update
sudo apt install -y git ffmpeg fonts-dejavu-core python3 python3-venv python3-pip
```

---

## 2. Клонирование навыка в конфигурацию OpenCode

```bash
mkdir -p ~/.config/opencode/skills
git clone https://github.com/Sereban-glitch/Sereban-glitch-video-montage.git ~/.config/opencode/skills/video-montage
```

*(Или по SSH, если ключ уже настроен: `git clone git@github.com:Sereban-glitch/Sereban-glitch-video-montage.git ~/.config/opencode/skills/video-montage`)*

---

## 3. Настройка виртуального окружения Python

В папке навыка или в любом проекте:

```bash
cd ~/.config/opencode/skills/video-montage
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install faster-whisper google-api-python-client google-auth-oauthlib Pillow numpy
```

---

## 4. Восстановление доступа к YouTube

1. Скачай файл ключа Google Cloud OAuth (`client_secret.json`) из консоли разработчика или личного бэкапа.
2. Положи его в:
   ```bash
   mkdir -p ~/.config/youtube
   cp /path/to/client_secret.json ~/.config/youtube/client_secret.json
   chmod 600 ~/.config/youtube/client_secret.json
   ```
3. Запусти разовую авторизацию для создания токена:
   ```bash
   .venv/bin/python scripts/publish/auth_youtube.py --project .
   ```
   Откроется браузер, выбери канал `daers024@gmail.com` и подтверди доступ. Токен сохранится в `token.json`.

---

## 5. Проверка работоспособности

Проверь, что скрипты запускаются без ошибок:

```bash
.venv/bin/python scripts/short/render_short.py --help
.venv/bin/python scripts/short/thumb_short.py --help
.venv/bin/python scripts/long/transcribe.py --help
.venv/bin/python scripts/publish/upload_youtube.py --help
```

Если `--help` выводится корректно — среда готова к работе.
