"""The size hook (section 5 of the design) and the `size` command."""
import json
import os
import re
import subprocess
import sys

import config
import handoff
import messages
import registry


def size_mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except (OSError, TypeError):
        return 0.0


def unattended_active(cfg):
    """True when the configured status command matches `active_pattern`; any failure is no."""
    un = cfg.get("unattended")
    if not isinstance(un, dict) or not un.get("status_command"):
        return False
    try:
        out = subprocess.run(un["status_command"], capture_output=True, text=True, timeout=3)
        return out.returncode == 0 and re.search(un.get("active_pattern", "^$"), out.stdout,
                                                  re.MULTILINE) is not None
    except (OSError, subprocess.SubprocessError, re.error, TypeError):
        return False


def starts_night(cfg, prompt):
    un = cfg.get("unattended")
    if not isinstance(un, dict):
        return False
    text = (prompt or "").strip().lower()
    return any(text.startswith(p.lower()) for p in un.get("start_prefixes", []) if p)


def decide(cfg, mb, prompt, has_pending):
    """(context for the session, message for the maintainer); either may be None."""
    lang, un = cfg["lang"], cfg.get("unattended")
    n = "%.0f" % mb
    if isinstance(un, dict) and unattended_active(cfg):
        if mb >= un.get("ceiling_mb", 1000):
            return messages.ctx("ceiling", mb=n), None
        return None, None
    pending_line = messages.user(lang, "pending") if has_pending else None
    if mb >= cfg["warn_mb"] and starts_night(cfg, prompt):
        return messages.ctx("night", mb=n), messages.user(lang, "night", mb=n)
    if mb >= cfg["tell_user_mb"]:
        lines = [messages.user(lang, "big", mb=n), pending_line]
        return messages.ctx("warn", mb=n), "\n".join(x for x in lines if x)
    if mb >= cfg["warn_mb"]:
        return messages.ctx("warn", mb=n), pending_line
    return None, pending_line


def emit(event_name, context, message):
    out = {}
    if context:
        out["hookSpecificOutput"] = {"hookEventName": event_name, "additionalContext": context}
    if message:
        out["systemMessage"] = message
    if out:
        print(json.dumps(out))


def hook(event):
    ident = registry.from_event(event)
    cfg = config.load_project(ident.cwd)
    mb = size_mb(event.get("transcript_path"))
    has_pending = handoff.latest_pending(ident.cwd, ident.handoff_name) is not None
    context, message = decide(cfg, mb, event.get("prompt", ""), has_pending)
    emit("UserPromptSubmit", context, message)
    return 0


def run_command(ident, path):
    if path is None and ident.session_id:
        path = os.path.join(config.claude_dir(), "projects", config.slug(ident.cwd),
                            ident.session_id + ".jsonl")
    if path is None:
        print("no transcript: give a path", file=sys.stderr)
        return 2
    cfg = config.load_project(ident.cwd)
    mb = size_mb(path)
    has_pending = handoff.latest_pending(ident.cwd, ident.handoff_name) is not None
    context, message = decide(cfg, mb, "", has_pending)
    print("%s: %.1f MB" % (path, mb))
    print("to the session: " + (context or "nothing"))
    print("to the maintainer: " + (message or "nothing"))
    return 0
