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


DEFAULT_MODES = ["auto", "dontAsk", "bypassPermissions"]


def bad_mode(cfg, mode):
    """The permission mode when it would stop a night on a permission request, else None (N3)."""
    if not mode:
        return None
    modes = cfg["unattended"].get("modes", DEFAULT_MODES)
    return None if mode in modes else mode


def decide(cfg, mb, prompt, has_pending, mode=None):
    """(context for the session, message for the maintainer); either may be None."""
    lang, un = cfg["lang"], cfg.get("unattended")
    n = "%.0f" % mb
    pending_line = messages.user(lang, "pending") if has_pending else None
    # S2 and N3 first: the status command runs in parallel and may already report the night.
    if starts_night(cfg, prompt):
        ctxs, msgs = [], []
        if mb >= cfg["warn_mb"]:
            ctxs.append(messages.ctx("night", mb=n))
            msgs.append(messages.user(lang, "night", mb=n))
        wrong = bad_mode(cfg, mode)
        if wrong:
            ctxs.append(messages.ctx("mode", mode=wrong))
            msgs.append(messages.user(lang, "mode", mode=wrong))
        if ctxs:
            return " ".join(ctxs), "\n".join(msgs)
    if isinstance(un, dict) and unattended_active(cfg):
        if mb >= un.get("ceiling_mb", 1000):
            return messages.ctx("ceiling", mb=n), None
        return None, None
    warn = messages.ctx("pending" if has_pending else "warn", mb=n)
    if mb >= cfg["tell_user_mb"]:
        lines = [messages.user(lang, "big", mb=n), pending_line]
        return warn, "\n".join(x for x in lines if x)
    if mb >= cfg["warn_mb"]:
        return warn, pending_line
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
    context, message = decide(cfg, mb, event.get("prompt", ""), has_pending,
                              event.get("permission_mode"))
    emit("UserPromptSubmit", context, message)
    return 0


def run_command(ident, path):
    if path is None and ident.session_id:
        path = config.transcript_path(ident.cwd, ident.session_id)
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
