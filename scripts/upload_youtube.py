#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

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
    meta = json.loads((project / "metadata.json").read_text(encoding="utf-8"))

    token = resolve(project, yt.get("token", "token.json"))
    expected = yt.get("expected_channel_id", "")
    if not expected:
        raise SystemExit("youtube.expected_channel_id is required")
    if not token.exists():
        raise SystemExit(f"token not found: {token} (run auth_youtube.py)")

    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise SystemExit("token is invalid and cannot be refreshed")

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ch = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    item = ch["items"][0]
    print("CHANNEL:", item["id"], item["snippet"]["title"], flush=True)
    if item["id"] != expected:
        raise SystemExit(f"wrong channel: {item['id']} != {expected}")

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": meta["categoryId"],
            "defaultLanguage": meta.get("defaultLanguage", "uk"),
            "defaultAudioLanguage": meta.get("defaultAudioLanguage", "uk"),
        },
        "status": {
            "privacyStatus": meta.get("privacyStatus", "private"),
            "selfDeclaredMadeForKids": meta.get("selfDeclaredMadeForKids", False),
            "embeddable": meta.get("embeddable", True),
            "license": "youtube",
        },
    }

    video = resolve(project, yt.get("video", "final.mp4"))
    thumb = resolve(project, yt.get("thumbnail", "thumbnail.jpg"))
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=bool(yt.get("notify_subscribers", False)),
    )

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"UPLOAD {int(status.progress() * 100)}%", flush=True)
            retry = 0
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503, 504) and retry < 6:
                retry += 1
                wait = 2 ** retry
                print(f"RETRY {retry} after {wait}s: {e}", flush=True)
                time.sleep(wait)
            else:
                raise

    video_id = response["id"]
    print("VIDEO_ID:", video_id, flush=True)

    if thumb.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg"),
            ).execute()
            print("THUMBNAIL: ok", flush=True)
        except Exception as e:
            print("THUMBNAIL ERROR:", e, flush=True)

    result = {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "studio": f"https://studio.youtube.com/video/{video_id}/edit",
        "title": meta["title"],
        "privacy": meta.get("privacyStatus", "private"),
        "channel": item["snippet"]["title"],
    }
    (project / "upload_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("DONE", result, flush=True)


if __name__ == "__main__":
    main()
