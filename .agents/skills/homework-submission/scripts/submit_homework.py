#!/usr/bin/env python3
"""Submit Markdown homework to the course Homework Submission API.

Stdlib only. It intentionally keeps secrets out of logs and receipts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "https://hw.sekachev.ee"
DEFAULT_TOKEN_ENV = "HOMEWORK_API_TOKEN"
DEFAULT_USER_AGENT = "CodexHomeworkClient/1.0"
CONTENT_LIMIT_BYTES = 262_144


def find_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "AGENTS.md").exists():
            return candidate
    return p


def load_dotenv(root: Path) -> None:
    """Load simple KEY=VALUE pairs from .env if not already set."""
    env_path = root / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_content(path: Path) -> bytes:
    if not path.exists():
        raise SystemExit(f"content file not found: {path}")
    data = path.read_bytes()
    if not data.strip():
        raise SystemExit("content_md is empty")
    if len(data) > CONTENT_LIMIT_BYTES:
        raise SystemExit(f"content_md is too large: {len(data)} bytes > {CONTENT_LIMIT_BYTES}")
    return data


def request_json(method: str, url: str, headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    body = None
    req_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json",
        **(headers or {}),
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers = {**req_headers, "Content-Type": "application/json"}

    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: dict[str, Any] | str = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise SystemExit(f"network error: {exc}") from exc


def save_receipt(root: Path, assignment_id: str, receipt: dict[str, Any], request_summary: dict[str, Any]) -> Path:
    out_dir = root / "homework" / "submissions"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_assignment = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in assignment_id).strip("-") or "assignment"
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{safe_assignment}--{ts}.json"
    payload = {
        "saved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "request": request_summary,
        "response": receipt,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit Markdown homework to Homework Submission API")
    parser.add_argument("--api-url", default=os.environ.get("HOMEWORK_API_URL", DEFAULT_API_URL), help="Base API URL")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing bearer token")
    parser.add_argument("--health", action="store_true", help="Check /healthz and exit")
    parser.add_argument("--assignment-id", help="Assignment ID, e.g. lesson-01")
    parser.add_argument("--student-id", help="Student ID, e.g. student-7")
    parser.add_argument("--student-name", default=None, help="Student name; omit for null")
    parser.add_argument("--agent-name", default=None, help="Agent name; omit for null")
    parser.add_argument("--content-file", type=Path, help="Markdown file to send as content_md")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print payload summary without sending")
    parser.add_argument("--save-receipt", action="store_true", help="Save successful response to homework/submissions")
    return parser.parse_args()


def main() -> None:
    root = find_root()
    load_dotenv(root)
    args = parse_args()
    api_url = str(args.api_url).rstrip("/")

    if args.health:
        status, body = request_json("GET", f"{api_url}/healthz")
        print(json.dumps({"status_code": status, "body": body}, ensure_ascii=False, indent=2))
        raise SystemExit(0 if status == 200 else 1)

    missing = [
        name
        for name, value in {
            "--assignment-id": args.assignment_id,
            "--student-id": args.student_id,
            "--content-file": args.content_file,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("missing required arguments: " + ", ".join(missing))

    content_bytes = read_content(args.content_file)
    content_md = content_bytes.decode("utf-8")
    content_sha = hashlib.sha256(content_bytes).hexdigest()

    payload = {
        "assignment_id": args.assignment_id,
        "student_id": args.student_id,
        "student_name": args.student_name,
        "agent_name": args.agent_name,
        "content_md": content_md,
    }
    summary = {
        "assignment_id": args.assignment_id,
        "student_id": args.student_id,
        "student_name": args.student_name,
        "agent_name": args.agent_name,
        "content_file": str(args.content_file),
        "bytes": len(content_bytes),
        "sha256": content_sha,
        "api_url": api_url,
    }

    if args.dry_run:
        print(json.dumps({"dry_run": True, "request_summary": summary}, ensure_ascii=False, indent=2))
        return

    token = os.environ.get(args.token_env)
    if not token or token == "PASTE_HOMEWORK_API_TOKEN_HERE":
        raise SystemExit(f"{args.token_env} is not set. Configure it as an environment variable or in local .env")

    status, body = request_json(
        "POST",
        f"{api_url}/v1/submissions",
        headers={"Authorization": f"Bearer {token}"},
        payload=payload,
    )

    result: dict[str, Any] = {
        "status_code": status,
        "body": body,
        "request_summary": summary,
    }

    if status != 201:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    if isinstance(body, dict):
        receipt_path = None
        if args.save_receipt:
            receipt_path = save_receipt(root, args.assignment_id, body, summary)
            result["receipt_path"] = str(receipt_path.relative_to(root))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except UnicodeDecodeError as exc:
        raise SystemExit(f"content file must be valid UTF-8 Markdown: {exc}") from exc
