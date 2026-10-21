"""Handoff files: `~/.session-crew/<slug>/<name>/<UTC stamp>-<sid8>.md`."""
import datetime
import glob
import os
import sys

import config

SECTIONS = [
    "## Work under way",
    "## His last requests and decisions",
    "## What remains",
    "## Where things are",
]


def name_dir(cwd, name):
    return os.path.join(config.project_dir(cwd), name)


def check_body(body):
    """Return the first missing section heading, or None; the sections must come in order."""
    pos = 0
    for heading in SECTIONS:
        at = -1
        for line_start in _line_starts(body):
            if line_start >= pos and body.startswith(heading, line_start):
                at = line_start
                break
        if at < 0:
            return heading
        pos = at + len(heading)
    return None


def _line_starts(text):
    yield 0
    for i, ch in enumerate(text):
        if ch == "\n":
            yield i + 1


def parse(path):
    """(meta dict, body) of a handoff file."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            for line in text[4:end].split("\n"):
                key, _, value = line.partition(": ")
                meta[key.strip()] = value.strip()
            body = text[end + 5:]
    return meta, body


def _write(path, meta, body):
    head = "".join("%s: %s\n" % (k, v) for k, v in meta.items())
    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n" + head + "---\n" + body)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def save(ident, body):
    """Write a pending handoff for `ident`; returns its path."""
    missing = check_body(body)
    if missing:
        raise ValueError("handoff body is missing the section: " + missing)
    folder = name_dir(ident.cwd, ident.handoff_name)
    os.makedirs(folder, exist_ok=True)
    stamp = now()
    path = os.path.join(folder, "%s-%s.md" % (stamp.strftime("%Y%m%dT%H%M%SZ"), ident.sid8))
    meta = {"status": "pending", "name": ident.handoff_name, "cwd": ident.cwd,
            "session_id": ident.session_id or "", "written_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ")}
    earlier = pending(ident.cwd, ident.handoff_name)
    _write(path, meta, body if body.endswith("\n") else body + "\n")
    for old, _ in earlier:
        _supersede(old, os.path.basename(path))
    return path


def pending(cwd, name=None):
    """Pending handoffs of a folder (of one name, or of every name), oldest first."""
    pattern = os.path.join(config.project_dir(cwd), name or "*", "*.md")
    out = []
    for path in glob.glob(pattern):
        try:
            meta, _ = parse(path)
        except OSError:
            continue
        if meta.get("status") == "pending":
            out.append((path, meta))
    out.sort(key=lambda pm: os.path.basename(pm[0]))
    return out


def latest_pending(cwd, name=None):
    items = pending(cwd, name)
    return items[-1] if items else None


def mark_used(path, used_by):
    meta, body = parse(path)
    meta["status"] = "used"
    meta["used_at"] = now().strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["used_by"] = used_by or ""
    _write(path, meta, body)


def _supersede(path, new_name):
    meta, body = parse(path)
    meta["status"] = "superseded"
    meta["superseded_by"] = new_name
    _write(path, meta, body)


def run_save(ident):
    try:
        path = save(ident, sys.stdin.read())
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(path)
    return 0


def run_status(ident):
    for path, meta in pending(ident.cwd):
        print("%s  %s  %s" % (meta.get("name", ""), meta.get("written_at", ""), path))
    return 0
