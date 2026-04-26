#!/usr/bin/env python3
"""Smoke-test homework helper scripts without network or token."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SUBMIT = ROOT / ".agents" / "skills" / "homework-submission" / "scripts" / "submit_homework.py"
DISCOVER = ROOT / ".agents" / "skills" / "homework-submission" / "scripts" / "discover_homework.py"
DRAFT = ROOT / "homework" / "drafts" / "smoke-test.md"


def run(label: str, args: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"{label} failed: {result.returncode}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")
    print(f"ok: {label}")
    return result.stdout


def main() -> None:
    DRAFT.parent.mkdir(parents=True, exist_ok=True)
    DRAFT.write_text("# Smoke test homework\n\nDone.\n", encoding="utf-8")

    out = run(
        "submit dry-run",
        [
            str(SUBMIT),
            "--assignment-id",
            "lesson-smoke",
            "--student-id",
            "student-smoke",
            "--student-name",
            "Smoke Student",
            "--agent-name",
            "Smoke Agent",
            "--content-file",
            str(DRAFT),
            "--dry-run",
        ],
    )
    json.loads(out)

    out = run("discover missing/empty course", [str(DISCOVER), "--course-dir", "course", "--format", "json"])
    json.loads(out)

    try:
        DRAFT.unlink()
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
