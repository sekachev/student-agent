#!/usr/bin/env python3
"""
Codex hook helper for the Student Codex Learning Agent.

This script is deterministic. It does not call an LLM and does not summarize
memories by itself. It only:

1. tells Codex which memory files and recent logs should be loaded at session start;
2. checks whether dreaming is due;
3. adds a lightweight homework reminder context based on system date and course schedule;
4. asks Codex to continue once at Stop when memory consolidation is due.

The semantic work is done by the agent following AGENTS.md and skills.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
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
HOMEWORK_KEYWORDS = [
    "домаш",
    "дз",
    "задани",
    "практик",
    "самостоятель",
    "homework",
    "assignment",
    "exercise",
    "task",
    "practice",
    "submit",
]


def read_stdin_json() -> dict[str, Any]:
    """Read the Codex hook payload and fail open if stdin is unavailable."""
    try:
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def find_root(payload: dict[str, Any]) -> Path:
    """Find the agent root without relying on git."""
    cwd = payload.get("cwd") or os.getcwd()
    p = Path(cwd).expanduser().resolve()

    for candidate in [p, *p.parents]:
        if (candidate / "AGENTS.md").exists() and (candidate / ".codex" / "hooks" / "dreaming.py").exists():
            return candidate

    for candidate in [p, *p.parents]:
        if (candidate / "AGENTS.md").exists():
            return candidate

    return p


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def parse_yaml_date(text: str, key: str) -> dt.date | None:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}|null)\s*$", text, re.M)
    if not match or match.group(1) == "null":
        return None
    try:
        return dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def parse_yaml_int(text: str, key: str, default: int) -> int:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(\d+)\s*$", text, re.M)
    if not match:
        return default
    try:
        return int(match.group(1))
    except ValueError:
        return default


def parse_yaml_string(text: str, key: str, default: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s*:\s*\"?([^\"\n]+)\"?\s*$", text, re.M)
    if not match:
        return default
    value = match.group(1).strip()
    return value if value and value != "null" else default


def list_daily_logs(root: Path) -> list[tuple[dt.date, Path]]:
    logs_dir = root / "logs" / "daily"
    if not logs_dir.exists():
        return []

    out: list[tuple[dt.date, Path]] = []
    for path in logs_dir.glob("*.md"):
        m = DATE_RE.search(path.name)
        if not m:
            continue
        try:
            out.append((dt.date.fromisoformat(m.group(1)), path))
        except ValueError:
            continue
    return sorted(out, key=lambda item: item[0])


def onboarding_pending(root: Path) -> bool:
    text = "\n".join(read_text(root / name) for name in ("SOUL.md", "STUDENT.md"))
    return "onboarding_status: pending" in text or "onboarding_status: null" in text


def dreaming_state(root: Path) -> dict[str, Any]:
    memory_text = read_text(root / "MEMORY.md")
    last_dream = parse_yaml_date(memory_text, "last_dream")
    window_days = parse_yaml_int(memory_text, "dream_window_days", 3)
    dream_after_new_logs = parse_yaml_int(memory_text, "dream_after_new_logs", 3)
    today = dt.date.today()
    logs = list_daily_logs(root)

    if last_dream is None:
        new_logs = logs
    else:
        new_logs = [(d, p) for d, p in logs if d > last_dream]

    reasons: list[str] = []
    if last_dream is None and len(logs) >= dream_after_new_logs:
        reasons.append(f"no last_dream and {len(logs)} daily logs exist")
    if last_dream is not None and (today - last_dream).days >= 7:
        reasons.append(f"last_dream is {(today - last_dream).days} days old")
    if len(new_logs) >= dream_after_new_logs:
        reasons.append(f"{len(new_logs)} new daily logs since last_dream")

    recent_logs = logs[-window_days:] if window_days > 0 else []
    return {
        "today": today.isoformat(),
        "last_dream": last_dream.isoformat() if last_dream else None,
        "window_days": window_days,
        "dream_after_new_logs": dream_after_new_logs,
        "log_count": len(logs),
        "new_log_count": len(new_logs),
        "recent_logs": [str(p.relative_to(root)) for _, p in recent_logs],
        "due": bool(reasons),
        "reasons": reasons,
    }


def parse_schedule_text(text: str) -> list[dict[str, Any]]:
    """Parse either compact Russian SCHEDULE.md or the ISO table in COURSE.md."""
    out: list[dict[str, Any]] = []

    # COURSE.md table: | 1 | 2026-04-27 | понедельник | Topic |
    table_pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.M)
    for match in table_pattern.finditer(text):
        try:
            dt.date.fromisoformat(match.group(2))
        except ValueError:
            continue
        out.append(
            {
                "lesson": int(match.group(1)),
                "date": match.group(2),
                "weekday": " ".join(match.group(3).split()),
                "topic": " ".join(match.group(4).split()),
            }
        )
    if out:
        return out

    # Raw SCHEDULE.md: 1. `27 апреля 2026, понедельник` — Topic 2. `30 апреля ...`
    raw_pattern = re.compile(
        r"(\d+)\.\s*`(\d{1,2})\s+([А-Яа-яёЁ]+)\s+(\d{4}),\s*([^`]+?)`\s*—\s*(.*?)(?=\s+\d+\.\s*`|\s*##|\Z)",
        re.S,
    )
    for match in raw_pattern.finditer(text):
        month = MONTHS_RU.get(match.group(3).lower())
        if not month:
            continue
        try:
            date = dt.date(int(match.group(4)), month, int(match.group(2)))
        except ValueError:
            continue
        out.append(
            {
                "lesson": int(match.group(1)),
                "date": date.isoformat(),
                "weekday": " ".join(match.group(5).split()),
                "topic": " ".join(match.group(6).split()),
            }
        )
    return out


def nearest_lessons(schedule: list[dict[str, Any]], today: dt.date) -> dict[str, Any]:
    parsed: list[tuple[dt.date, dict[str, Any]]] = []
    for item in schedule:
        try:
            parsed.append((dt.date.fromisoformat(item["date"]), item))
        except Exception:
            continue
    parsed.sort(key=lambda pair: pair[0])
    if not parsed:
        return {"current_or_previous": None, "next": None, "days_to_next": None}
    previous = [item for date, item in parsed if date <= today]
    upcoming = [(date, item) for date, item in parsed if date >= today]
    next_date, next_item = upcoming[0] if upcoming else (None, None)
    return {
        "current_or_previous": previous[-1] if previous else None,
        "next": next_item,
        "days_to_next": (next_date - today).days if next_date else None,
    }


def scan_homework_candidates(course_dir: Path, lesson_number: int | None = None, limit: int = 8) -> list[str]:
    if not course_dir.exists():
        return []

    module_roots: list[Path] = []
    if lesson_number and 1 <= lesson_number <= 10:
        module_roots.append(course_dir / f"Module_{lesson_number:02d}")
        if lesson_number > 1:
            module_roots.append(course_dir / f"Module_{lesson_number - 1:02d}")
        if lesson_number < 10:
            module_roots.append(course_dir / f"Module_{lesson_number + 1:02d}")
    module_roots.extend(sorted(course_dir.glob("Module_*")))

    seen_roots: list[Path] = []
    for root in module_roots:
        if root.exists() and root not in seen_roots:
            seen_roots.append(root)

    candidates: list[str] = []
    for root in seen_roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".canvas"}:
                continue
            rel_text = str(path.relative_to(course_dir)).lower()
            if any(kw in rel_text for kw in HOMEWORK_KEYWORDS):
                candidates.append(str(path.relative_to(course_dir)))
            else:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")[:100_000].lower()
                except Exception:
                    text = ""
                if any(kw in text for kw in HOMEWORK_KEYWORDS):
                    candidates.append(str(path.relative_to(course_dir)))
            if len(candidates) >= limit:
                return candidates
    return candidates


def homework_state(root: Path) -> dict[str, Any]:
    today = dt.date.today()
    course_text = read_text(root / "COURSE.md")
    student_text = read_text(root / "STUDENT.md")
    course_local = parse_yaml_string(course_text, "course_local_path", "course/").strip().rstrip("/") or "course"
    remind_before_days = parse_yaml_int(course_text, "homework_remind_before_days", 2)
    course_dir = root / course_local

    schedule_text = read_text(course_dir / "SCHEDULE.md") if course_dir.exists() else ""
    schedule = parse_schedule_text(schedule_text) or parse_schedule_text(course_text)
    nearest = nearest_lessons(schedule, today)
    next_item = nearest.get("next")
    previous_item = nearest.get("current_or_previous")
    days_to_next = nearest.get("days_to_next")
    target_lesson = None
    if next_item:
        target_lesson = next_item.get("lesson")
    elif previous_item:
        target_lesson = previous_item.get("lesson")

    candidates = scan_homework_candidates(course_dir, target_lesson, limit=8) if course_dir.exists() else []
    has_submitted = "| submitted |" in student_text or "submitted" in student_text.lower()

    reminder = None
    if next_item and days_to_next is not None and days_to_next <= remind_before_days:
        reminder = (
            f"Next lesson is in {days_to_next} day(s): lesson {next_item['lesson']} on {next_item['date']} — {next_item['topic']}. "
            "Check whether homework is discovered/ready/submitted."
        )
    elif previous_item and not next_item:
        reminder = "Course schedule appears to be past the final lesson; check final-project status if relevant."

    return {
        "today": today.isoformat(),
        "course_local_path": course_local,
        "course_exists": course_dir.exists(),
        "next_lesson": next_item,
        "current_or_previous_lesson": previous_item,
        "days_to_next": days_to_next,
        "remind_before_days": remind_before_days,
        "homework_candidates": candidates,
        "any_submitted_marker": has_submitted,
        "reminder": reminder,
    }


def emit_json(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def session_start(root: Path, state: dict[str, Any], hw: dict[str, Any]) -> None:
    pending = onboarding_pending(root)
    due_text = "yes: " + "; ".join(state["reasons"]) if state["due"] else "no"
    recent = ", ".join(state["recent_logs"]) if state["recent_logs"] else "none"
    onboarding = "yes" if pending else "no"

    if hw["course_exists"]:
        course_line = f"course exists at {hw['course_local_path']}"
    else:
        course_line = f"course not found at {hw['course_local_path']}; ask to clone/connect it before deep homework discovery"

    next_lesson = hw.get("next_lesson")
    if next_lesson:
        lesson_line = f"next lesson {next_lesson['lesson']} on {next_lesson['date']}: {next_lesson['topic']} ({hw['days_to_next']} day(s) away)"
    else:
        lesson_line = "no upcoming lesson found in schedule"

    candidates = ", ".join(hw["homework_candidates"][:5]) if hw["homework_candidates"] else "none discovered by lightweight scan"
    reminder = hw.get("reminder") or "none"

    additional_context = (
        "Learning agent boot context:\n"
        "- Load AGENTS.md, SOUL.md, STUDENT.md, COURSE.md, MEMORY.md.\n"
        f"- System date according to hook: {state['today']}.\n"
        f"- Load only recent daily logs: {recent}.\n"
        "- Do not auto-load older logs unless needed for the current task or dreaming.\n"
        f"- Onboarding pending: {onboarding}.\n"
        f"- Dreaming due: {due_text}.\n"
        f"- Course status: {course_line}.\n"
        f"- Schedule: {lesson_line}.\n"
        f"- Homework reminder: {reminder}.\n"
        f"- Lightweight homework candidates: {candidates}.\n"
        "- If onboarding is pending, run the onboarding skill before normal course work.\n"
        "- If homework is due/relevant, briefly remind the student and use $homework-submission when finding/preparing/submitting homework.\n"
        "- If dreaming is due, run the Dreaming protocol from AGENTS.md before normal work."
    )
    emit_json(
        {
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": additional_context,
            },
        }
    )


def stop_hook(payload: dict[str, Any], state: dict[str, Any]) -> None:
    # Avoid infinite loops: Codex sets stop_hook_active when this hook already
    # continued the current turn.
    if payload.get("stop_hook_active"):
        emit_json({"continue": True})
        return

    if state["due"]:
        reason = (
            "Before completing this turn, run the Dreaming protocol from AGENTS.md. "
            "Consolidate daily logs since last_dream into MEMORY.md, update STUDENT.md progress and homework statuses, "
            "adjust SOUL.md only if there is durable evidence, update last_dream to today's date, "
            "and leave old logs as archive. Reasons: " + "; ".join(state["reasons"])
        )
        # In Codex Stop hooks, decision:block means “continue once with this reason”,
        # not “reject the user”.
        emit_json({"decision": "block", "reason": reason})
    else:
        emit_json({"continue": True})


def fail_open(mode: str, exc: BaseException) -> None:
    # Stop hooks require valid JSON on stdout. Keep the session usable even if
    # memory files are malformed. Print diagnostics to stderr only.
    print(f"learning-agent hook failed open in {mode}: {exc}", file=sys.stderr)
    emit_json(
        {
            "continue": True,
            "systemMessage": (
                "Learning-agent hook failed open. Continue normally; "
                "inspect .codex/hooks/dreaming.py if automatic memory/homework reminders are needed."
            ),
        }
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "session-start"
    try:
        payload = read_stdin_json()
        root = find_root(payload)
        state = dreaming_state(root)
        if mode == "stop":
            stop_hook(payload, state)
        else:
            hw = homework_state(root)
            session_start(root, state, hw)
    except BaseException as exc:  # intentionally broad: hooks must not brick Codex
        fail_open(mode, exc)


if __name__ == "__main__":
    main()
