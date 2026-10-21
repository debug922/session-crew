"""The rename hook (section 6 of the design): free a name and give it to this session."""
import json
import os
import signal
import time

import config
import handoff
import messages
import registry

WAIT_S = 5.0


def _output(title=None, context=None):
    inner = {"hookEventName": "UserPromptSubmit"}
    if title:
        inner["sessionTitle"] = title
    if context:
        inner["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": inner}))


def _stop(pid):
    """SIGTERM, then wait up to WAIT_S for the pid to go; True when it is gone."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if not registry.pid_alive(pid):
            return True
        time.sleep(0.1)
    return not registry.pid_alive(pid)


def hook(event):
    words = (event.get("prompt") or "").strip().split()
    if len(words) != 2 or words[0] != "/migrate" or not config.NAME_RE.fullmatch(words[1]):
        return 0
    name = words[1]
    ident = registry.from_event(event)
    if ident.name == name:
        return 0
    if handoff.latest_pending(ident.cwd, name) is None:
        return 0
    found = registry.holders(name, ident.cwd, ident.session_id)
    if not found:
        _output(title=name)
        return 0
    for holder in found:
        if holder.get("status") != "idle":
            _output(context=messages.ctx("busy", name=name, pid=holder["pid"]))
            return 0
    for holder in found:
        if not _stop(holder["pid"]):
            _output(context=messages.ctx("stuck", name=name, pid=holder["pid"]))
            return 0
    _output(title=name)
    return 0
