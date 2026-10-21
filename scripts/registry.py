"""The Claude Code session registry (`<claude>/sessions/<pid>.json`) and who a script is."""
import glob
import json
import os
import subprocess

import config


def sessions_dir():
    return os.path.join(config.claude_dir(), "sessions")


def read_all():
    """Every registry file as a dict (with `pid` taken from the file name if absent)."""
    out = []
    for path in glob.glob(os.path.join(sessions_dir(), "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if not isinstance(data.get("pid"), int):
            try:
                data["pid"] = int(os.path.basename(path)[:-5])
            except ValueError:
                continue
        out.append(data)
    return out


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    # A zombie still answers signal 0 but is gone for our purposes.
    try:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                              text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return True
    return not stat.startswith("Z")


def find_by_session_id(session_id):
    for entry in read_all():
        if entry.get("sessionId") == session_id:
            return entry
    return None


def parent_pid(pid):
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=3).stdout.strip()
        return int(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def find_by_ancestry():
    """Walk up the parent pids to the first one with a registry file."""
    by_pid = {e["pid"]: e for e in read_all()}
    pid, seen = os.getpid(), set()
    while pid > 1 and pid not in seen:
        if pid in by_pid:
            return by_pid[pid]
        seen.add(pid)
        pid = parent_pid(pid)
    return None


def holders(name, cwd, own_session_id=None):
    """Live sessions in this folder called `name`, other than the caller's own."""
    out = []
    for e in read_all():
        if e.get("name") != name or e.get("cwd") != cwd:
            continue
        if own_session_id and e.get("sessionId") == own_session_id:
            continue
        if e["pid"] == os.getpid() or not pid_alive(e["pid"]):
            continue
        out.append(e)
    return out


class Identity:
    def __init__(self, name=None, session_id=None, cwd=None, pid=None):
        self.name, self.session_id, self.cwd, self.pid = name, session_id, cwd, pid

    @property
    def sid8(self):
        return (self.session_id or "00000000")[:8]

    @property
    def handoff_name(self):
        """The name handoffs are filed under: the session's, or `unnamed-<sid8>`."""
        return config.safe_name(self.name) if self.name else "unnamed-" + self.sid8


def from_event(event):
    """Identity inside a hook: the registry file whose sessionId equals the event's."""
    sid = event.get("session_id")
    entry = find_by_session_id(sid) if sid else None
    entry = entry or {}
    return Identity(entry.get("name") or None, sid or entry.get("sessionId"),
                    event.get("cwd") or entry.get("cwd") or os.getcwd(), entry.get("pid"))


def from_command_line(name=None, session_id=None, cwd=None):
    entry = find_by_session_id(session_id) if session_id else find_by_ancestry()
    entry = entry or {}
    return Identity(name or entry.get("name") or None,
                    session_id or entry.get("sessionId"),
                    cwd or entry.get("cwd") or os.getcwd(), entry.get("pid"))
