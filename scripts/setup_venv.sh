#!/bin/bash
set -euo pipefail

PROJECT="${1:-.}"
cd "$PROJECT"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install faster-whisper google-api-python-client google-auth-oauthlib Pillow numpy

echo "VENV_OK $PROJECT/.venv"
