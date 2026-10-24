#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    yt = cfg.get("youtube", {})

    client = resolve(project, yt.get("client_secret", "~/.config/youtube/client_secret.json"))
    token = resolve(project, yt.get("token", "token.json"))
    login_hint = yt.get("login_hint", "")

    if not client.exists():
        raise SystemExit(f"client_secret not found: {client}")

    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    kwargs = {
        "prompt": "consent",
        "authorization_prompt_message": "OPEN_URL: {url}",
    }
    if login_hint:
        kwargs["login_hint"] = login_hint
    creds = flow.run_local_server(port=0, open_browser=True, **kwargs)
    token.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token, 0o600)
    print(f"AUTH_OK token={token} refresh={bool(creds.refresh_token)}", flush=True)


if __name__ == "__main__":
    main()
