#!/usr/bin/env python3
"""Discover likely homework files/snippets in a local course checkout.

This is a deterministic helper for the learning agent. It does not decide what
is homework; it surfaces candidates for the agent/student to inspect.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

KEYWORDS = [
    "домаш",
    "дз",
    "задани",
    "практик",
    "самостоятель",
    "отчёт",
    "отчет",
    "сдать",
    "homework",
    "assignment",
    "exercise",
    "task",
    "practice",
    "submit",
    "deliverable",
]
TEXT_EXTENSIONS = {".md", ".txt", ".canvas"}
MONTHS_RU = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def parse_schedule(course_dir: Path) -> list[dict[str, Any]]:
    path = course_dir / "SCHEDULE.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    # Handles compact one-line schedules like:
    # 1. `27 апреля 2026, понедельник` — Topic 2. `30 апреля ...`
    pattern = re.compile(
        r"(\d+)\.\s*`(\d{1,2})\s+([А-Яа-яёЁ]+)\s+(\d{4}),\s*([^`]+?)`\s*—\s*(.*?)(?=\s+\d+\.\s*`|\s*##|\Z)",
        re.S,
    )
    out: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        n = int(match.group(1))
        day = int(match.group(2))
        month_name = match.group(3).lower()
        year = int(match.group(4))
        weekday = " ".join(match.group(5).split())
        topic = " ".join(match.group(6).split())
        month = MONTHS_RU.get(month_name)
        if not month:
            continue
        try:
            date = dt.date(year, month, day)
        except ValueError:
            continue
        out.append({"lesson": n, "date": date.isoformat(), "weekday": weekday, "topic": topic})
    return out


def nearest_lessons(schedule: list[dict[str, Any]], today: dt.date) -> dict[str, Any]:
    if not schedule:
        return {}
    parsed: list[tuple[dt.date, dict[str, Any]]] = []
    for item in schedule:
        try:
            parsed.append((dt.date.fromisoformat(item["date"]), item))
        except Exception:
            pass
    parsed.sort(key=lambda x: x[0])
    previous = [item for date, item in parsed if date <= today]
    upcoming = [item for date, item in parsed if date >= today]
    return {
        "current_or_previous": previous[-1] if previous else None,
        "next": upcoming[0] if upcoming else None,
    }


def normalize_module(module: str | None) -> str | None:
    if not module:
        return None
    m = re.search(r"(\d+)", module)
    if not m:
        return module
    return f"Module_{int(m.group(1)):02d}"


def iter_candidate_files(course_dir: Path, module: str | None) -> list[Path]:
    roots: list[Path]
    if module:
        roots = [course_dir / module]
    else:
        roots = sorted(course_dir.glob("Module_*"))
        if not roots:
            roots = [course_dir]

    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
                files.append(path)
    return files


def extract_snippet(text: str, keyword: str, radius: int = 240) -> str:
    lower = text.lower()
    idx = lower.find(keyword.lower())
    if idx < 0:
        return ""
    start = max(0, idx - radius)
    end = min(len(text), idx + len(keyword) + radius)
    snippet = text[start:end]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


def discover(course_dir: Path, module: str | None, limit: int) -> list[dict[str, Any]]:
    normalized = normalize_module(module)
    results: list[dict[str, Any]] = []
    for path in iter_candidate_files(course_dir, normalized):
        rel = path.relative_to(course_dir)
        rel_lower = str(rel).lower()
        filename_hits = [kw for kw in KEYWORDS if kw in rel_lower]
        text = path.read_text(encoding="utf-8", errors="replace")[:500_000]
        text_lower = text.lower()
        text_hits = [kw for kw in KEYWORDS if kw in text_lower]
        hits = sorted(set(filename_hits + text_hits))
        if not hits:
            continue
        first_hit = hits[0]
        snippet = extract_snippet(text, first_hit)
        results.append(
            {
                "path": str(rel),
                "module": rel.parts[0] if rel.parts else None,
                "hits": hits,
                "snippet": snippet,
            }
        )
        if len(results) >= limit:
            break
    return results


def render_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Homework discovery", ""]
    lines.append(f"Course dir: `{payload['course_dir']}`")
    lines.append(f"Today: `{payload['today']}`")
    if payload.get("nearest"):
        nearest = payload["nearest"]
        if nearest.get("current_or_previous"):
            item = nearest["current_or_previous"]
            lines.append(f"Current/previous lesson: `{item['lesson']}` — `{item['date']}` — {item['topic']}")
        if nearest.get("next"):
            item = nearest["next"]
            lines.append(f"Next lesson: `{item['lesson']}` — `{item['date']}` — {item['topic']}")
    lines.append("")
    if not payload["candidates"]:
        lines.append("No homework candidates found with the configured keywords.")
        return "\n".join(lines) + "\n"
    lines.append("## Candidates")
    lines.append("")
    for item in payload["candidates"]:
        lines.append(f"### `{item['path']}`")
        lines.append(f"- Module: `{item.get('module')}`")
        lines.append(f"- Hits: {', '.join(item['hits'])}")
        if item.get("snippet"):
            lines.append(f"- Snippet: {item['snippet']}")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover homework candidates in course modules")
    parser.add_argument("--course-dir", type=Path, default=Path("course"))
    parser.add_argument("--module", help="Module name or number, e.g. Module_03 or 3")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    course_dir = args.course_dir
    today = dt.date.today()
    if not course_dir.exists():
        payload = {
            "course_dir": str(course_dir),
            "today": today.isoformat(),
            "error": "course directory not found",
            "candidates": [],
            "schedule": [],
            "nearest": {},
        }
    else:
        schedule = parse_schedule(course_dir)
        payload = {
            "course_dir": str(course_dir),
            "today": today.isoformat(),
            "module": normalize_module(args.module),
            "schedule": schedule,
            "nearest": nearest_lessons(schedule, today),
            "candidates": discover(course_dir, args.module, args.limit),
        }
    if args.format == "markdown":
        print(render_markdown(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
