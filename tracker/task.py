#!/usr/bin/env python3
"""CLI for the project task ledger (tracker/pending.json).

Replaces hand-written throwaway scripts for updating the ledger. Every
mutating command validates the whole ledger in memory before writing,
writes atomically (temp file + os.replace), and re-renders
tracker/PENDING.html afterwards unless --no-render is given.

Examples:
    python tracker/task.py add --id my-task --human "sugom Thai" --ai "english summary"
    python tracker/task.py done --id my-task --human "finished, works"
    python tracker/task.py update --id my-task --state willdo
    python tracker/task.py archive --days 14
    python tracker/task.py list --state doing
    python tracker/task.py validate

Long/multiline text (e.g. Thai) can be supplied from a UTF-8 file instead
of a shell argument: --human "@path\\to\\file.txt".
"""
from __future__ import annotations

import argparse
import datetime
import difflib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LEDGER_NAME = "pending.json"
ARCHIVE_NAME = "pending_archive.json"
RENDER_SCRIPT = HERE / "render_pending.py"

STATES = ("doing", "willdo", "done")
ICT_TZ = datetime.timezone(datetime.timedelta(hours=7))
TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S"
TIMESTAMP_PARSE_FMT = TIMESTAMP_FMT + "%z"
SUGGESTION_COUNT = 5
SUGGESTION_CUTOFF = 0.4  # difflib similarity ratio floor; keeps "Did you mean" to plausible typos only


# ---- time helpers -----------------------------------------------------------


def now_ict() -> datetime.datetime:
    """Current time in Bangkok (ICT, UTC+7)."""
    return datetime.datetime.now(ICT_TZ)


def format_ts(dt: datetime.datetime) -> str:
    """Format a datetime as the ledger's timestamp convention: +0700, no colon."""
    return dt.strftime(TIMESTAMP_FMT) + "+0700"


def parse_ts(raw: str) -> datetime.datetime:
    """Parse a ledger timestamp string back into an aware datetime."""
    return datetime.datetime.strptime(raw, TIMESTAMP_PARSE_FMT)


# ---- ledger path helpers -----------------------------------------------------


def ledger_path(dir_: Path) -> Path:
    """Path to the main ledger (pending.json) inside dir_."""
    return dir_ / LEDGER_NAME


def archive_path(dir_: Path) -> Path:
    """Path to the archive ledger (pending_archive.json) inside dir_."""
    return dir_ / ARCHIVE_NAME


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"ledger not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON via temp file + os.replace so a crash never truncates the target."""
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_task_", suffix=".json", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


# ---- validation ---------------------------------------------------------------


def validate_ledger(data: Any) -> list[str]:
    """Full schema check. Returns a list of human-readable error strings (empty = valid)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["ledger root must be a JSON object"]

    for key in ("project", "title", "updated", "tasks"):
        if key not in data:
            errors.append(f"missing top-level field: {key}")

    tasks = data.get("tasks")
    if tasks is None:
        return errors
    if not isinstance(tasks, list):
        errors.append("tasks must be a list")
        return errors

    seen_ids: set[str] = set()
    for i, t in enumerate(tasks):
        prefix = f"tasks[{i}]"
        if not isinstance(t, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        tid = t.get("id")
        if not isinstance(tid, str) or not tid.strip():
            errors.append(f"{prefix}: id must be a non-empty string")
            tid = tid if isinstance(tid, str) else f"<{prefix}>"
        elif tid in seen_ids:
            errors.append(f"duplicate id: {tid}")
        else:
            seen_ids.add(tid)

        state = t.get("state")
        if state not in STATES:
            errors.append(f"{prefix} ({tid}): state must be one of {STATES}, got {state!r}")

        for field in ("human", "ai"):
            val = t.get(field)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{prefix} ({tid}): {field} must be a non-empty string")

        for field in ("created", "updated"):
            val = t.get(field)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{prefix} ({tid}): {field} must be a non-empty string")
            else:
                try:
                    parse_ts(val)
                except ValueError:
                    errors.append(f"{prefix} ({tid}): {field} is not a parseable timestamp: {val!r}")

        agent = t.get("agent")
        if agent is not None and not isinstance(agent, str):
            errors.append(f"{prefix} ({tid}): agent must be a string")

        skills = t.get("skills", [])
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            errors.append(f"{prefix} ({tid}): skills must be a list of strings")

        files = t.get("files", [])
        if not isinstance(files, list):
            errors.append(f"{prefix} ({tid}): files must be a list")
        else:
            for j, fentry in enumerate(files):
                path_val = fentry.get("path") if isinstance(fentry, dict) else None
                if not isinstance(fentry, dict) or not isinstance(path_val, str) or not path_val.strip():
                    errors.append(f"{prefix} ({tid}): files[{j}].path must be a non-empty string")
                    continue
                label = fentry.get("label")
                if label is not None and not isinstance(label, str):
                    errors.append(f"{prefix} ({tid}): files[{j}].label must be a string")

    return errors


# ---- small parsing helpers ----------------------------------------------------


def resolve_value(raw: str) -> str:
    """Return raw as-is, unless it starts with '@' -> read that file (UTF-8).

    A single trailing newline (the kind editors add on save) is stripped so
    the ledger stores exactly the intended text; any further trailing blank
    lines are preserved as part of the content.
    """
    if raw is None or not raw.startswith("@"):
        return raw
    file_ref = raw[1:]
    if not file_ref:
        raise ValueError("empty @file path (use '@path/to/file.txt')")
    file_path = Path(file_ref)
    content = file_path.read_text(encoding="utf-8")
    if content.endswith("\r\n"):
        return content[:-2]
    if content.endswith("\n"):
        return content[:-1]
    return content


def parse_skills(raw: str | None) -> list[str]:
    """Comma-separated string -> list of trimmed, non-empty skill names."""
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def parse_files(raw_list: list[str] | None) -> list[dict[str, str]]:
    """Repeated "path::label" CLI args -> ledger files[] entries (label optional)."""
    if not raw_list:
        return []
    out = []
    for item in raw_list:
        if "::" in item:
            path_str, label = item.split("::", 1)
        else:
            path_str, label = item, None
        entry: dict[str, str] = {"path": path_str.strip()}
        if label and label.strip():
            entry["label"] = label.strip()
        out.append(entry)
    return out


def suggest_ids(target: str, candidates: list[str], n: int = SUGGESTION_COUNT) -> list[str]:
    """Up to n existing ids plausibly similar to target (typo-distance), not just the closest of an unrelated set."""
    return difflib.get_close_matches(target, candidates, n=n, cutoff=SUGGESTION_CUTOFF)


# ---- render ---------------------------------------------------------------


def run_render(no_render: bool) -> None:
    """Invoke render_pending.py to refresh PENDING.html; report failure, keep the JSON write."""
    if no_render:
        return
    result = subprocess.run(
        [sys.executable, str(RENDER_SCRIPT)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"WARN: render_pending.py exited {result.returncode} (data saved, view not updated)")


# ---- validate-then-write helper -------------------------------------------


def _validate_or_report(data: dict[str, Any], what: str) -> list[str]:
    """Validate data; print errors (ASCII) if any. Caller must not write on non-empty return."""
    errors = validate_ledger(data)
    if errors:
        print(f"ERROR: {what} failed validation, not written:")
        for e in errors:
            print(f"  - {e}")
    return errors


# ---- commands ---------------------------------------------------------------


def cmd_add(args: argparse.Namespace, dir_: Path) -> int:
    """Insert a new task at the top of tasks[]; fail if args.id already exists."""
    path = ledger_path(dir_)
    data = load_json(path)
    tasks = data.setdefault("tasks", [])

    if any(t.get("id") == args.id for t in tasks):
        print(f"ERROR: task id already exists: {args.id}")
        return 1

    ts = format_ts(now_ict())
    new_task = {
        "id": args.id,
        "state": args.state,
        "created": ts,
        "updated": ts,
        "agent": args.agent or "",
        "skills": parse_skills(args.skills),
        "files": parse_files(args.file),
        "ai": resolve_value(args.ai),
        "human": resolve_value(args.human),
    }
    tasks.insert(0, new_task)
    data["updated"] = ts

    if _validate_or_report(data, "ledger"):
        return 1

    atomic_write_json(path, data)
    print(f"OK: added task {args.id} (state={args.state})")
    run_render(args.no_render)
    return 0


def _apply_update(
    dir_: Path,
    task_id: str,
    *,
    state: str | None = None,
    human: str | None = None,
    ai: str | None = None,
    agent: str | None = None,
    skills: str | None = None,
    files: list[str] | None = None,
    no_render: bool = False,
) -> int:
    """Shared core for update/done: change only the fields passed (not None)."""
    path = ledger_path(dir_)
    data = load_json(path)
    tasks = data.get("tasks", [])
    t = next((x for x in tasks if x.get("id") == task_id), None)

    if t is None:
        ids = [x.get("id", "") for x in tasks]
        closest = suggest_ids(task_id, ids)
        print(f"ERROR: unknown task id: {task_id}")
        if closest:
            print("Did you mean one of:")
            for c in closest:
                print(f"  - {c}")
        return 1

    if state is not None:
        t["state"] = state
    if human is not None:
        t["human"] = resolve_value(human)
    if ai is not None:
        t["ai"] = resolve_value(ai)
    if agent is not None:
        t["agent"] = agent
    if skills is not None:
        t["skills"] = parse_skills(skills)
    if files is not None:
        t["files"] = parse_files(files)

    ts = format_ts(now_ict())
    t["updated"] = ts
    data["updated"] = ts

    if _validate_or_report(data, "ledger"):
        return 1

    atomic_write_json(path, data)
    print(f"OK: updated task {task_id}")
    run_render(no_render)
    return 0


def cmd_update(args: argparse.Namespace, dir_: Path) -> int:
    """Partial update of an existing task by id."""
    return _apply_update(
        dir_,
        args.id,
        state=args.state,
        human=args.human,
        ai=args.ai,
        agent=args.agent,
        skills=args.skills,
        files=args.file,
        no_render=args.no_render,
    )


def cmd_done(args: argparse.Namespace, dir_: Path) -> int:
    """Sugar for "update --state done"."""
    return _apply_update(
        dir_,
        args.id,
        state="done",
        human=args.human,
        ai=args.ai,
        no_render=args.no_render,
    )


def cmd_archive(args: argparse.Namespace, dir_: Path) -> int:
    """Move done tasks older than args.days into pending_archive.json. Never touches doing/willdo."""
    path = ledger_path(dir_)
    apath = archive_path(dir_)
    data = load_json(path)

    if _validate_or_report(data, "ledger"):
        return 1

    tasks = data.get("tasks", [])

    cutoff = now_ict() - datetime.timedelta(days=args.days)
    to_archive = []
    remaining = []
    for t in tasks:
        if t.get("state") == "done":
            try:
                updated_dt = parse_ts(t.get("updated", ""))
            except (ValueError, TypeError):
                remaining.append(t)  # can't determine age -> never lose it
                continue
            if updated_dt < cutoff:
                to_archive.append(t)
                continue
        remaining.append(t)

    if not to_archive:
        print("OK: 0 tasks archived")
        return 0

    if args.dry_run:
        print(f"DRY-RUN: would archive {len(to_archive)} task(s):")
        for t in to_archive:
            print(f"  - {t.get('id')}")
        return 0

    if apath.exists():
        archive_data = load_json(apath)
    else:
        archive_data = {
            "project": data.get("project", ""),
            "title": data.get("title", ""),
            "updated": "",
            "tasks": [],
        }
    archive_data.setdefault("tasks", []).extend(to_archive)
    ts = format_ts(now_ict())
    archive_data["updated"] = ts

    if _validate_or_report(archive_data, "archive"):
        return 1

    data["tasks"] = remaining
    data["updated"] = ts

    if _validate_or_report(data, "ledger"):
        return 1

    # write archive first: if the second write fails, a task may be
    # duplicated (still in main + in archive) but is never lost.
    atomic_write_json(apath, archive_data)
    atomic_write_json(path, data)
    print(f"OK: archived {len(to_archive)} task(s)")
    run_render(args.no_render)
    return 0


def cmd_list(args: argparse.Namespace, dir_: Path) -> int:
    """Print a compact ASCII table of tasks (state, id, updated), optionally filtered by state."""
    path = ledger_path(dir_)
    data = load_json(path)
    tasks = data.get("tasks", [])
    if args.state:
        tasks = [t for t in tasks if t.get("state") == args.state]

    if not tasks:
        print("(no tasks)")
        return 0

    id_w = max(max(len(t.get("id", "")) for t in tasks), 2)
    state_w = max(max(len(t.get("state", "")) for t in tasks), 5)
    header = f"{'STATE':<{state_w}}  {'ID':<{id_w}}  UPDATED"
    print(header)
    print("-" * len(header))
    for t in tasks:
        print(f"{t.get('state', ''):<{state_w}}  {t.get('id', ''):<{id_w}}  {t.get('updated', '')}")
    return 0


def cmd_validate(args: argparse.Namespace, dir_: Path) -> int:
    """Full schema check of the ledger; exit 0 if valid, 1 otherwise."""
    path = ledger_path(dir_)
    data = load_json(path)
    errors = validate_ledger(data)
    if errors:
        print(f"INVALID: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("OK: ledger is valid")
    return 0


# ---- argparse -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the add/update/done/archive/list/validate argparse CLI."""
    dir_only = argparse.ArgumentParser(add_help=False)
    dir_only.add_argument("--dir", default=None, help="override tracker directory (for tests)")

    common = argparse.ArgumentParser(add_help=False, parents=[dir_only])
    common.add_argument("--no-render", action="store_true", help="skip auto-render after mutation")

    parser = argparse.ArgumentParser(
        prog="task.py",
        description="CLI for the project task ledger (tracker/pending.json).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", parents=[common], help="add a new task at the top of the ledger")
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--human", required=True, help='text, or "@path" to read from a UTF-8 file')
    p_add.add_argument("--ai", required=True, help='text, or "@path" to read from a UTF-8 file')
    p_add.add_argument("--state", default="doing", choices=STATES)
    p_add.add_argument("--agent", default="")
    p_add.add_argument("--skills", default=None, help="comma-separated list, e.g. a,b,c")
    p_add.add_argument("--file", action="append", default=None, help='repeatable "path::label" (label optional)')
    p_add.set_defaults(func=cmd_add)

    p_update = sub.add_parser("update", parents=[common], help="partially update an existing task")
    p_update.add_argument("--id", required=True)
    p_update.add_argument("--state", default=None, choices=STATES)
    p_update.add_argument("--human", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_update.add_argument("--ai", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_update.add_argument("--agent", default=None)
    p_update.add_argument("--skills", default=None, help="comma-separated list, replaces skills")
    p_update.add_argument(
        "--file", action="append", default=None,
        help='repeatable "path::label" (label optional); REPLACES the files list when given',
    )
    p_update.set_defaults(func=cmd_update)

    p_done = sub.add_parser("done", parents=[common], help='shortcut for "update --state done"')
    p_done.add_argument("--id", required=True)
    p_done.add_argument("--human", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_done.add_argument("--ai", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_done.set_defaults(func=cmd_done)

    p_archive = sub.add_parser("archive", parents=[common], help="move stale done tasks to pending_archive.json")
    p_archive.add_argument("--days", type=int, default=14)
    p_archive.add_argument("--dry-run", action="store_true")
    p_archive.set_defaults(func=cmd_archive)

    p_list = sub.add_parser("list", parents=[dir_only], help="show a compact table of tasks")
    p_list.add_argument("--state", default=None, choices=STATES)
    p_list.set_defaults(func=cmd_list)

    p_validate = sub.add_parser("validate", parents=[dir_only], help="validate the ledger schema")
    p_validate.set_defaults(func=cmd_validate)

    return parser


def _make_streams_replace_errors() -> None:
    """Make stdout/stderr replace un-encodable characters instead of crashing.

    Windows consoles are often cp1252/cp874 and cannot encode arbitrary Unicode
    (e.g. a Thai task id). Without this, printing such text raises
    UnicodeEncodeError AFTER a write may have already succeeded, turning a
    successful mutation into a false failure exit.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass  # stream doesn't support reconfigure (e.g. some test doubles) -- best effort


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, resolve the target dir, dispatch to the subcommand."""
    _make_streams_replace_errors()
    parser = build_parser()
    args = parser.parse_args(argv)
    dir_ = Path(args.dir).resolve() if args.dir else HERE

    # render_pending.py hardcodes its own paths and always renders the LIVE
    # ledger next to this script -- rendering while operating on a different
    # --dir would silently render the wrong file. Force-skip and say so.
    if hasattr(args, "no_render") and dir_ != HERE and not args.no_render:
        print("NOTE: render skipped (--dir override always targets the live ledger's render script)")
        args.no_render = True

    try:
        return args.func(args, dir_)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: ledger is not valid JSON: {e}")
        return 1
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
