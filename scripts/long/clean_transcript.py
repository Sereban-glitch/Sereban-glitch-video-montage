#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path


def resolve(project: Path, value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else project / p


SYSTEM = (
    "You are a careful Ukrainian subtitle editor. Output only a valid JSON array, "
    "no markdown, no explanations. Never add facts or rewrite the meaning. Preserve "
    "the original wording as much as possible; if a word is unclear, keep the closest "
    "original form instead of inventing a new fact."
)

PROMPT = """Нижче сегменти автоматичного розпізнавання судового засідання українською.
Виправ очевидні помилки розпізнавання, розділові знаки, великі літери та правопис юридичних термінів і власних назв. Не переписуй зміст, не додавай фактів, не скорочуй.
Поверни ТІЛЬКИ JSON-масив об'єктів {"id": <number>, "text": "<text>"}.
Сегменти:
"""


def call_llm(url: str, key: str, model: str, max_tokens: int, batch: list) -> dict | None:
    payload = [{"id": s["id"], "text": s["text"]} for s in batch]
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": PROMPT + json.dumps(payload, ensure_ascii=False)}],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.load(r)
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    if resp.get("stop_reason") == "max_tokens":
        return None
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return None
    return {int(x["id"]): str(x["text"]).strip() for x in arr if "id" in x and "text" in x}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg_path = Path(args.config).expanduser() if args.config else project / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    data = json.loads(resolve(project, cfg["transcript"]).read_text(encoding="utf-8"))

    markers = cfg.get("artifact_markers", ["Дякую за перегляд"])
    segs = [s for s in data["segments"] if not any(m in s["text"] for m in markers)]
    print(f"segments={len(data['segments'])} after_artifacts={len(segs)}", flush=True)

    gem = cfg.get("gemini", {})
    url = gem.get("url", "http://127.0.0.1:18080/v1/messages")
    model = gem.get("model", "gemini-2.5-flash")
    max_tokens = int(gem.get("max_tokens", 4096))
    batch_size = int(gem.get("batch_size", 15))
    key_file = Path(gem.get("key_file", "~/.config/antigravity-proxy/api-key")).expanduser()
    key = key_file.read_text().strip() if key_file.exists() else ""
    if not key:
        print("WARNING: Gemini key not found, keeping raw text", flush=True)

    by_id = {}
    llm_failures = 0
    queue = [segs[i:i + batch_size] for i in range(0, len(segs), batch_size)]
    while queue:
        batch = queue.pop(0)
        print(f"batch {batch[0]['id']}..{batch[-1]['id']} ({len(batch)})", flush=True)
        got = None
        if key:
            try:
                got = call_llm(url, key, model, max_tokens, batch)
            except Exception as e:
                llm_failures += 1
                print(f"  LLM error: {e}", flush=True)
                if llm_failures >= 3:
                    print("  disabling LLM for remaining batches", flush=True)
                    key = ""
        if got is None:
            if not key:
                print("  keeping originals", flush=True)
            elif len(batch) == 1:
                print("  keeping original", flush=True)
            else:
                mid = max(1, len(batch) // 2)
                print("  retry smaller", flush=True)
                queue.insert(0, batch[mid:])
                queue.insert(0, batch[:mid])
                time.sleep(1)
            continue
        by_id.update(got)
        print(f"  ok {len(got)}", flush=True)
        time.sleep(1)

    fixes = {int(k): str(v) for k, v in cfg.get("text_fixes", {}).items()}
    out = dict(data)
    out["segments"] = []
    changed = 0
    for s in segs:
        s = dict(s)
        s["text_raw"] = s["text"]
        s["text"] = fixes.get(s["id"], by_id.get(s["id"], s["text"]))
        if s["text"] != s["text_raw"]:
            changed += 1
        out["segments"].append(s)

    out_path = resolve(project, cfg["clean_transcript"])
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DONE fixed={changed} of {len(out['segments'])} -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
