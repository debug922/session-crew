"""Recover a session's state from its old transcript when no handoff exists."""
import glob
import json
import os
import sys

import config

CHUNK = 8 * 1024 * 1024
MAX_READ = 200 * 1024 * 1024  # one budget for a whole `recover` run
MAX_TITLE = 16 * 1024 * 1024  # at most this much of one candidate, looking for its title
MAX_LINE = 32 * 1024 * 1024
MAX_CANDIDATES = 10
PART_CUT = 2000
TOTAL_CUT = 40 * 1024


class Budget:
    def __init__(self, left):
        self.left = left

    def spend(self, n):
        self.left -= n


def reverse_lines(path, budget, cap=None, chunk=None):
    """Lines of a file from the last to the first.

    Reads at most `cap` bytes (default: all the budget) and charges every byte to `budget`.
    A single line longer than MAX_LINE is dropped, not accumulated.
    """
    chunk = chunk or CHUNK
    with open(path, "rb") as f:
        pos = f.seek(0, os.SEEK_END)
        stop = max(0, pos - min(cap or budget.left, budget.left))
        carry, skipping = b"", False
        while pos > stop:
            start = max(stop, pos - chunk)
            f.seek(start)
            data = f.read(pos - start)
            budget.spend(pos - start)
            pos = start
            if skipping:
                cut = data.rfind(b"\n")
                if cut < 0:
                    continue
                data, skipping = data[:cut + 1], False
            else:
                data += carry
            parts = data.split(b"\n")
            if pos > stop:
                carry, parts = parts[0], parts[1:]
                if len(carry) > MAX_LINE:
                    carry, skipping = b"", True
            else:
                carry = b""
                if stop > 0:
                    parts = parts[1:]  # cut by the read limit: partial, dropped
            for line in reversed(parts):
                if line and len(line) <= MAX_LINE:
                    yield line


def _loads(line):
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def last_title(path, budget):
    for line in reverse_lines(path, budget, cap=MAX_TITLE):
        if b'"custom-title"' in line:
            rec = _loads(line)
            if rec and rec.get("type") == "custom-title":
                return rec.get("customTitle")
    return None


def find_transcript(cwd, name, budget, exclude_sid=None):
    files = []
    for folder in config.transcript_dirs(cwd):
        files += glob.glob(os.path.join(folder, "*.jsonl"))
    files.sort(key=os.path.getmtime, reverse=True)
    files = [p for p in files if os.path.basename(p)[:-6] != exclude_sid]
    for path in files[:MAX_CANDIDATES]:
        if budget.left <= 0:
            break
        if last_title(path, budget) == name:
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


def extract(path, budget):
    """(last compaction summary or None, [(role, text)] after it, oldest first).

    The summary has a budget of its own (TOTAL_CUT); so do the messages after it. When the
    message budget is spent the reading goes on back for the summary, collecting nothing.
    """
    left, summary, msgs = TOTAL_CUT, None, []
    for line in reverse_lines(path, budget):
        if left <= 0 and b"isCompactSummary" not in line:
            continue
        if b'"user"' not in line and b'"assistant"' not in line:
            continue
        rec = _loads(line)
        if not rec or rec.get("type") not in ("user", "assistant"):
            continue
        text = _text(rec).strip()
        if rec.get("type") == "user" and rec.get("isCompactSummary"):
            summary = text[:TOTAL_CUT]
            break
        if text and left > 0:
            text = text[:min(PART_CUT, left)]
            left -= len(text)
            msgs.append((rec["type"], text))
    msgs.reverse()
    return summary, msgs


def run(ident, name):
    if not name:
        print("no name to recover: give one", file=sys.stderr)
        return 2
    budget = Budget(MAX_READ)
    path = find_transcript(ident.cwd, name, budget, ident.session_id)
    if not path:
        print("Nothing to recover: no earlier transcript in this folder is called %s." % name)
        return 0
    summary, msgs = extract(path, budget)
    print("# Recovered from %s\n" % path)
    print("## Last compaction summary\n")
    print(summary if summary else "(none found)")
    print("\n## Conversation after it\n")
    for role, text in msgs:
        print("[%s] %s\n" % (role, text))
    return 0
