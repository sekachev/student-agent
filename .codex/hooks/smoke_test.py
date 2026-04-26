#!/usr/bin/env python3
"""Smoke-test the project-local Codex hooks without requiring git."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".codex" / "hooks" / "dreaming.py"
HOOKS_JSON = ROOT / ".codex" / "hooks.json"


def assert_json(stdout: str, label: str) -> None:
    try:
        json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} did not emit valid JSON: {exc}\n{stdout}")


def run_direct(mode: str, payload: dict) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"direct {mode} exited {result.returncode}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
    assert_json(result.stdout, f"direct {mode}")
    print(f"ok: direct {mode}")


def run_configured(label: str, command: str, payload: dict, cwd: Path) -> None:
    result = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"configured {label} exited {result.returncode}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
    assert_json(result.stdout, f"configured {label}")
    print(f"ok: configured {label}")


def main() -> None:
    payload = {
        "session_id": "smoke-test",
        "transcript_path": None,
        "cwd": str(ROOT),
        "model": "smoke-test",
    }
    run_direct("session-start", {**payload, "hook_event_name": "SessionStart", "source": "startup"})
    run_direct("stop", {**payload, "hook_event_name": "Stop", "turn_id": "smoke-test", "stop_hook_active": False})

    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    start_cmd = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    stop_cmd = hooks["hooks"]["Stop"][0]["hooks"][0]["command"]
    subdir = ROOT / "logs" / "daily"

    run_configured(
        "session-start from root",
        start_cmd,
        {**payload, "hook_event_name": "SessionStart", "source": "startup"},
        ROOT,
    )
    run_configured(
        "stop from root",
        stop_cmd,
        {**payload, "hook_event_name": "Stop", "turn_id": "smoke-test", "stop_hook_active": False},
        ROOT,
    )
    run_configured(
        "session-start from subdir",
        start_cmd,
        {**payload, "cwd": str(subdir), "hook_event_name": "SessionStart", "source": "startup"},
        subdir,
    )
    run_configured(
        "stop from subdir",
        stop_cmd,
        {**payload, "cwd": str(subdir), "hook_event_name": "Stop", "turn_id": "smoke-test", "stop_hook_active": False},
        subdir,
    )


if __name__ == "__main__":
    main()
