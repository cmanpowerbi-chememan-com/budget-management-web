#!/usr/bin/env python3
"""CLI for the project task ledger (tracker/pending.json) — AI-only, v2.

The ledger is the hand-over channel between AI tools (Claude Code / Kimi Code);
session history is not shared, this file is. There is NO human view: the
`human` field and PENDING.html/render_pending.py are retired and stripped.

Every mutating command validates the whole ledger in memory before writing and
writes atomically (temp file + os.replace). Every mutation also auto-housekeeps:
  - dedups `log-<hash>` autolog entries once a real entry quotes the hash
  - archives done tasks older than ARCHIVE_DAYS into pending_archive.json
  - strips retired keys (`human`) and empty optional fields (agent/skills/files)

Automation: `.git/hooks/post-commit` calls `task.py autolog <hash> <subject>`
after every commit, so committed work always lands in the ledger even if the
session forgets to log it.

Examples:
    python tracker/task.py add --id my-task --ai "english summary" --agent kimi
    python tracker/task.py done --id my-task --ai "finished, commit 1a2b3c4, leftovers"
    python tracker/task.py update --id my-task --state willdo
    python tracker/task.py autolog 1a2b3c4d... "commit subject"   # called by git hook
    python tracker/task.py check                                  # commits missing from ledger
    python tracker/task.py compact                                # strip retired fields + archive stale
    python tracker/task.py list --state doing
    python tracker/task.py validate

Long/multiline text can be supplied from a UTF-8 file instead of a shell
argument: --ai "@path\\to\\file.txt".
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

STATES = ("doing", "willdo", "done")
ICT_TZ = datetime.timezone(datetime.timedelta(hours=7))
TIMESTAMP_FMT = "%Y-%m-%dT%H:%M:%S"
TIMESTAMP_PARSE_FMT = TIMESTAMP_FMT + "%z"
SUGGESTION_COUNT = 5
SUGGESTION_CUTOFF = 0.4  # difflib similarity ratio floor; keeps "Did you mean" to plausible typos only

ARCHIVE_DAYS = 30          # done tasks older than this move to pending_archive.json on every write
AUTOLOG_PREFIX = "log-"    # id prefix for hook-created entries: log-<short hash>
RETIRED_KEYS = ("human",)  # stripped on every write
OPTIONAL_KEYS = ("agent", "skills", "files")  # omitted from JSON when empty


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


# ---- normalization / housekeeping --------------------------------------------


def normalize_task(t: dict[str, Any]) -> None:
    """In-place: drop retired keys (human) and empty optional fields (agent/skills/files)."""
    for key in RETIRED_KEYS:
        t.pop(key, None)
    for key in OPTIONAL_KEYS:
        if not t.get(key):
            t.pop(key, None)


def dedup_autolog(tasks: list[dict[str, Any]]) -> list[str]:
    """Remove log-<hash> entries whose hash is quoted in any real entry's ai text.

    Returns the list of removed autolog ids. Mutates `tasks` in place.
    """
    real_texts = [
        str(t.get("ai", "")) for t in tasks
        if not str(t.get("id", "")).startswith(AUTOLOG_PREFIX)
    ]
    removed: list[str] = []
    kept: list[dict[str, Any]] = []
    for t in tasks:
        tid = str(t.get("id", ""))
        if tid.startswith(AUTOLOG_PREFIX):
            short = tid[len(AUTOLOG_PREFIX):]
            if short and any(short in txt for txt in real_texts):
                removed.append(tid)
                continue
        kept.append(t)
    tasks[:] = kept
    return removed


def split_stale_done(tasks: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Move done tasks older than `days` out of `tasks` (in place); return them.

    Tasks with unparseable timestamps are kept (never lose data).
    """
    cutoff = now_ict() - datetime.timedelta(days=days)
    stale: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    for t in tasks:
        if t.get("state") == "done":
            try:
                updated_dt = parse_ts(t.get("updated", ""))
            except (ValueError, TypeError):
                remaining.append(t)
                continue
            if updated_dt < cutoff:
                stale.append(t)
                continue
        remaining.append(t)
    tasks[:] = remaining
    return stale


def housekeep(data: dict[str, Any], dir_: Path) -> tuple[list[str], list[str]]:
    """Normalize + dedup + archive stale done. Returns (deduped_ids, archived_ids).

    Writes the archive file FIRST when needed: if the later main-ledger write
    fails, a task may be duplicated (main + archive) but is never lost.
    """
    tasks = data.setdefault("tasks", [])
    for t in tasks:
        if isinstance(t, dict):
            normalize_task(t)
    deduped = dedup_autolog(tasks)
    stale = split_stale_done(tasks, ARCHIVE_DAYS)
    archived_ids: list[str] = []
    if stale:
        apath = archive_path(dir_)
        if apath.exists():
            archive_data = load_json(apath)
        else:
            archive_data = {
                "project": data.get("project", ""),
                "title": data.get("title", ""),
                "updated": "",
                "tasks": [],
            }
        archive_data.setdefault("tasks", []).extend(stale)
        archive_data["updated"] = format_ts(now_ict())
        if _validate_or_report(archive_data, "archive"):
            raise ValueError("archive failed validation, not written")
        atomic_write_json(apath, archive_data)
        archived_ids = [str(t.get("id", "")) for t in stale]
    return deduped, archived_ids


def save_ledger(data: dict[str, Any], dir_: Path, housekeeping: tuple[list[str], list[str]]) -> int:
    """Validate + write the main ledger; print housekeeping summary. Returns exit code."""
    data["updated"] = format_ts(now_ict())
    if _validate_or_report(data, "ledger"):
        return 1
    atomic_write_json(ledger_path(dir_), data)
    deduped, archived = housekeeping
    if deduped:
        print(f"OK: deduped {len(deduped)} autolog entr(ies): {', '.join(deduped)}")
    if archived:
        print(f"OK: auto-archived {len(archived)} done task(s) older than {ARCHIVE_DAYS}d")
    return 0


# ---- validation ---------------------------------------------------------------


def validate_ledger(data: Any) -> list[str]:
    """Full schema check. Returns a list of readable error strings (empty = valid)."""
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

        ai = t.get("ai")
        if not isinstance(ai, str) or not ai.strip():
            errors.append(f"{prefix} ({tid}): ai must be a non-empty string")

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
    data = load_json(ledger_path(dir_))
    tasks = data.setdefault("tasks", [])

    if any(t.get("id") == args.id for t in tasks):
        print(f"ERROR: task id already exists: {args.id}")
        return 1

    ts = format_ts(now_ict())
    new_task: dict[str, Any] = {
        "id": args.id,
        "state": args.state,
        "created": ts,
        "updated": ts,
        "ai": resolve_value(args.ai),
    }
    if args.agent:
        new_task["agent"] = args.agent
    skills = parse_skills(args.skills)
    if skills:
        new_task["skills"] = skills
    files = parse_files(args.file)
    if files:
        new_task["files"] = files
    tasks.insert(0, new_task)

    hk = housekeep(data, dir_)
    rc = save_ledger(data, dir_, hk)
    if rc == 0:
        print(f"OK: added task {args.id} (state={args.state})")
    return rc


def _apply_update(
    dir_: Path,
    task_id: str,
    *,
    state: str | None = None,
    ai: str | None = None,
    agent: str | None = None,
    skills: str | None = None,
    files: list[str] | None = None,
) -> int:
    """Shared core for update/done: change only the fields passed (not None)."""
    data = load_json(ledger_path(dir_))
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
    if ai is not None:
        t["ai"] = resolve_value(ai)
    if agent is not None:
        t["agent"] = agent
    if skills is not None:
        t["skills"] = parse_skills(skills)
    if files is not None:
        t["files"] = parse_files(files)

    t["updated"] = format_ts(now_ict())

    hk = housekeep(data, dir_)
    rc = save_ledger(data, dir_, hk)
    if rc == 0:
        print(f"OK: updated task {task_id}")
    return rc


def cmd_update(args: argparse.Namespace, dir_: Path) -> int:
    """Partial update of an existing task by id."""
    return _apply_update(
        dir_,
        args.id,
        state=args.state,
        ai=args.ai,
        agent=args.agent,
        skills=args.skills,
        files=args.file,
    )


def cmd_done(args: argparse.Namespace, dir_: Path) -> int:
    """Sugar for "update --state done"."""
    return _apply_update(
        dir_,
        args.id,
        state="done",
        ai=args.ai,
    )


def cmd_archive(args: argparse.Namespace, dir_: Path) -> int:
    """Move done tasks older than args.days into pending_archive.json. Never touches doing/willdo."""
    data = load_json(ledger_path(dir_))
    if _validate_or_report(data, "ledger"):
        return 1

    tasks = data.get("tasks", [])
    if args.dry_run:
        probe = [dict(t) for t in tasks]
        stale = split_stale_done(probe, args.days)
        if not stale:
            print("OK: 0 tasks would be archived")
            return 0
        print(f"DRY-RUN: would archive {len(stale)} task(s):")
        for t in stale:
            print(f"  - {t.get('id')}")
        return 0

    stale = split_stale_done(tasks, args.days)
    if not stale:
        print("OK: 0 tasks archived")
        return 0

    # re-use housekeep's archive writer semantics manually (days overridden here)
    apath = archive_path(dir_)
    if apath.exists():
        archive_data = load_json(apath)
    else:
        archive_data = {
            "project": data.get("project", ""),
            "title": data.get("title", ""),
            "updated": "",
            "tasks": [],
        }
    archive_data.setdefault("tasks", []).extend(stale)
    archive_data["updated"] = format_ts(now_ict())
    if _validate_or_report(archive_data, "archive"):
        return 1
    # write archive first: a crash after this duplicates (main + archive) but never loses
    atomic_write_json(apath, archive_data)

    rc = save_ledger(data, dir_, ([], [str(t.get("id", "")) for t in stale]))
    if rc == 0:
        print(f"OK: archived {len(stale)} task(s)")
    return rc


def cmd_compact(args: argparse.Namespace, dir_: Path) -> int:
    """One-off/normalizing pass: strip retired fields, dedup autolog, archive stale done."""
    data = load_json(ledger_path(dir_))
    before = len(data.get("tasks", []))
    hk = housekeep(data, dir_)
    rc = save_ledger(data, dir_, hk)
    if rc == 0:
        after = len(data.get("tasks", []))
        print(f"OK: compacted ledger {before} -> {after} task(s)")
    return rc


def cmd_autolog(args: argparse.Namespace, dir_: Path) -> int:
    """Hook entry point: record a commit as log-<short> unless already referenced anywhere."""
    full_hash = args.hash.strip()
    short = full_hash[:7]
    if not short:
        print("ERROR: empty commit hash")
        return 1

    data = load_json(ledger_path(dir_))
    blob = json.dumps(data.get("tasks", []), ensure_ascii=False)
    apath = archive_path(dir_)
    if apath.exists():
        try:
            blob += json.dumps(load_json(apath).get("tasks", []), ensure_ascii=False)
        except (json.JSONDecodeError, OSError):
            pass  # unreadable archive must not block the commit hook
    if short in blob:
        print(f"OK: commit {short} already referenced in ledger")
        return 0

    ts = format_ts(now_ict())
    subject = " ".join(args.subject.split())  # collapse newlines/whitespace from git output
    tasks = data.setdefault("tasks", [])
    tasks.insert(0, {
        "id": AUTOLOG_PREFIX + short,
        "state": "done",
        "created": ts,
        "updated": ts,
        "agent": "autolog",
        "ai": f"{subject} [commit {short}]",
    })

    hk = housekeep(data, dir_)
    rc = save_ledger(data, dir_, hk)
    if rc == 0:
        print(f"OK: autologged commit {short}")
    return rc


def cmd_check(args: argparse.Namespace, dir_: Path) -> int:
    """Audit: list recent git commits whose hash appears nowhere in ledger or archive."""
    repo = dir_.parent
    result = subprocess.run(
        ["git", "log", f"-{args.n}", "--format=%h%x1f%s"],
        cwd=str(repo), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: git log failed in {repo}: {result.stderr.strip()}")
        return 1

    blob = json.dumps(load_json(ledger_path(dir_)).get("tasks", []), ensure_ascii=False)
    apath = archive_path(dir_)
    if apath.exists():
        blob += json.dumps(load_json(apath).get("tasks", []), ensure_ascii=False)

    missing: list[tuple[str, str]] = []
    total = 0
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        total += 1
        short, _, subject = line.partition("\x1f")
        if short not in blob:
            missing.append((short, subject))

    if not missing:
        print(f"OK: all {total} recent commit(s) referenced in ledger")
        return 0
    print(f"MISSING: {len(missing)} of {total} recent commit(s) not referenced in ledger:")
    for short, subject in missing:
        print(f"  - {short} {subject}")
    return 1


def cmd_list(args: argparse.Namespace, dir_: Path) -> int:
    """Print a compact ASCII table of tasks (state, id, updated), optionally filtered by state."""
    data = load_json(ledger_path(dir_))
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
    data = load_json(ledger_path(dir_))
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
    """Build the add/update/done/archive/autolog/check/compact/list/validate argparse CLI."""
    dir_only = argparse.ArgumentParser(add_help=False)
    dir_only.add_argument("--dir", default=None, help="override tracker directory (for tests)")

    parser = argparse.ArgumentParser(
        prog="task.py",
        description="CLI for the project task ledger (tracker/pending.json) — AI-only, no human view.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", parents=[dir_only], help="add a new task at the top of the ledger")
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--ai", required=True, help='text, or "@path" to read from a UTF-8 file')
    p_add.add_argument("--state", default="doing", choices=STATES)
    p_add.add_argument("--agent", default="")
    p_add.add_argument("--skills", default=None, help="comma-separated list, e.g. a,b,c")
    p_add.add_argument("--file", action="append", default=None, help='repeatable "path::label" (label optional)')
    p_add.set_defaults(func=cmd_add)

    p_update = sub.add_parser("update", parents=[dir_only], help="partially update an existing task")
    p_update.add_argument("--id", required=True)
    p_update.add_argument("--state", default=None, choices=STATES)
    p_update.add_argument("--ai", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_update.add_argument("--agent", default=None)
    p_update.add_argument("--skills", default=None, help="comma-separated list, replaces skills")
    p_update.add_argument(
        "--file", action="append", default=None,
        help='repeatable "path::label" (label optional); REPLACES the files list when given',
    )
    p_update.set_defaults(func=cmd_update)

    p_done = sub.add_parser("done", parents=[dir_only], help='shortcut for "update --state done"')
    p_done.add_argument("--id", required=True)
    p_done.add_argument("--ai", default=None, help='text, or "@path" to read from a UTF-8 file')
    p_done.set_defaults(func=cmd_done)

    p_archive = sub.add_parser("archive", parents=[dir_only], help="move stale done tasks to pending_archive.json")
    p_archive.add_argument("--days", type=int, default=ARCHIVE_DAYS)
    p_archive.add_argument("--dry-run", action="store_true")
    p_archive.set_defaults(func=cmd_archive)

    p_compact = sub.add_parser("compact", parents=[dir_only], help="strip retired fields, dedup autolog, archive stale done")
    p_compact.set_defaults(func=cmd_compact)

    p_autolog = sub.add_parser("autolog", parents=[dir_only], help="record a commit (called by .git/hooks/post-commit)")
    p_autolog.add_argument("hash")
    p_autolog.add_argument("subject")
    p_autolog.set_defaults(func=cmd_autolog)

    p_check = sub.add_parser("check", parents=[dir_only], help="list recent commits missing from the ledger")
    p_check.add_argument("-n", type=int, default=30, help="how many recent commits to inspect (default 30)")
    p_check.set_defaults(func=cmd_check)

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
