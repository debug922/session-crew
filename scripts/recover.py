"""Recover a session's state from its old transcript when no handoff exists."""
import glob
import json
import os
import sys

import config

CHUNK = 8 * 1024 * 1024
MAX_READ = 200 * 1024 * 1024
MAX_CANDIDATES = 10
PART_CUT = 2000
TOTAL_CUT = 40 * 1024


def reverse_lines(path, chunk=None, limit=None):
    """Lines of a file from the last to the first, reading at most `limit` bytes."""
    chunk, limit = chunk or CHUNK, limit or MAX_READ
    with open(path, "rb") as f:
        pos = f.seek(0, os.SEEK_END)
        stop = max(0, pos - limit)
        carry = b""
        while pos > stop:
            start = max(stop, pos - chunk)
            f.seek(start)
            data = f.read(pos - start) + carry
            pos = start
            parts = data.split(b"\n")
            if pos > stop:
                carry, parts = parts[0], parts[1:]
            else:
                carry = b""
                if stop > 0:
                    parts = parts[1:]  # cut by the read limit: partial, dropped
            for line in reversed(parts):
                if line:
                    yield line


def _loads(line):
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def last_title(path):
    for line in reverse_lines(path):
        if b'"custom-title"' in line:
            rec = _loads(line)
            if rec and rec.get("type") == "custom-title":
                return rec.get("customTitle")
    return None


def find_transcript(cwd, name, exclude_sid=None):
    folder = os.path.join(config.claude_dir(), "projects", config.slug(cwd))
    files = sorted(glob.glob(os.path.join(folder, "*.jsonl")), key=os.path.getmtime, reverse=True)
    files = [p for p in files if os.path.basename(p)[:-6] != exclude_sid]
    for path in files[:MAX_CANDIDATES]:
        if last_title(path) == name:
            return path
    return None


def _text(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def extract(path):
    """(last compaction summary or None, [(role, text)] after it, oldest first)."""
    budget, summary, msgs = TOTAL_CUT, None, []
    for line in reverse_lines(path):
        if b'"user"' not in line and b'"assistant"' not in line:
            continue
        rec = _loads(line)
        if not rec or rec.get("type") not in ("user", "assistant"):
            continue
        text = _text(rec).strip()
        if rec.get("type") == "user" and rec.get("isCompactSummary"):
            summary = text[:max(0, budget)]
            break
        if text and budget > 0:
            text = text[:min(PART_CUT, budget)]
            budget -= len(text)
            msgs.append((rec["type"], text))
    msgs.reverse()
    return summary, msgs


def run(ident, name):
    if not name:
        print("no name to recover: give one", file=sys.stderr)
        return 2
    path = find_transcript(ident.cwd, name, ident.session_id)
    if not path:
        print("Nothing to recover: no earlier transcript in this folder is called %s." % name)
        return 0
    summary, msgs = extract(path)
    print("# Recovered from %s\n" % path)
    print("## Last compaction summary\n")
    print(summary if summary else "(none found)")
    print("\n## Conversation after it\n")
    for role, text in msgs:
        print("[%s] %s\n" % (role, text))
    return 0
