#!/usr/bin/env python3
"""Verifies YouTube video processing status, privacy, duration, and thumbnail."""

import argparse
import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def main():
    ap = argparse.ArgumentParser(description="Verify uploaded YouTube video status")
    ap.add_argument("--project", default=".", help="Project directory containing upload_result.json or config.json")
    ap.add_argument("--video-id", default="", help="Specific YouTube video ID to check")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    video_id = args.video_id

    if not video_id:
        res_file = project / "upload_result.json"
        if res_file.exists():
            data = json.loads(res_file.read_text(encoding="utf-8"))
            video_id = data.get("video_id", "")
        if not video_id:
            sys.exit("Error: No video ID provided and upload_result.json not found or missing video_id.")

    # Locate token
    token_path = project / "token.json"
    if not token_path.exists():
        cfg_file = project / "config.json"
        if cfg_file.exists():
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            tok_rel = cfg.get("youtube", {}).get("token", "token.json")
            tok_candidate = (project / tok_rel).resolve()
            if tok_candidate.exists():
                token_path = tok_candidate

    if not token_path.exists():
        sys.exit(f"Error: OAuth token not found at {token_path}")

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    res = yt.videos().list(
        part="snippet,status,processingDetails,contentDetails",
        id=video_id
    ).execute()

    items = res.get("items", [])
    if not items:
        sys.exit(f"Error: Video {video_id} not found on YouTube.")

    item = items[0]
    title = item["snippet"].get("title", "")
    privacy = item["status"].get("privacyStatus", "")
    upload_status = item["status"].get("uploadStatus", "")
    proc_status = item.get("processingDetails", {}).get("processingStatus", "")
    duration = item["contentDetails"].get("duration", "")
    thumbs = list(item["snippet"].get("thumbnails", {}).keys())

    print(f"VIDEO_ID: {video_id}")
    print(f"TITLE: {title}")
    print(f"PRIVACY: {privacy}")
    print(f"UPLOAD_STATUS: {upload_status}")
    print(f"PROCESSING_STATUS: {proc_status}")
    print(f"DURATION: {duration}")
    print(f"THUMBNAILS: {thumbs}")

    if proc_status == "succeeded" and upload_status == "processed":
        print("VERIFICATION: SUCCESS")
    else:
        print(f"VERIFICATION: IN_PROGRESS (processing: {proc_status})")


if __name__ == "__main__":
    main()
