"""The rename hook (section 6 of the design): free a name and give it to this session."""
import json
import os
import re
import signal
import time

import config
import handoff
import messages
import registry

WAIT_S = 5.0
PROMPT_RE = re.compile(r"/migrate (%s)" % config.NAME_RE.pattern)


def _output(title=None, context=None):
    inner = {"hookEventName": "UserPromptSubmit"}
    if title:
        inner["sessionTitle"] = title
    if context:
        inner["additionalContext"] = context
    print(json.dumps({"hookSpecificOutput": inner}))


def _stop_all(pids):
    """SIGTERM every pid, then one shared wait of up to WAIT_S; the pids still alive."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.monotonic() + WAIT_S
    left = [p for p in pids if registry.pid_alive(p)]
    while left and time.monotonic() < deadline:
        time.sleep(0.1)
        left = [p for p in left if registry.pid_alive(p)]
    return left


def hook(event):
    m = PROMPT_RE.fullmatch((event.get("prompt") or "").strip())
    if not m:
        return 0
    name = m.group(1)
    ident = registry.from_event(event)
    if ident.name == name:
        return 0
    if handoff.latest_pending(ident.cwd, name) is None:
        return 0
    found = registry.holders(name, ident.cwd, ident.session_id, ident.pid)
    for holder in found:
        if not holder["verified"]:
            _output(context=messages.ctx("unverified", name=name, pid=holder["pid"]))
            return 0
        if holder.get("status") != "idle":
            _output(context=messages.ctx("busy", name=name, pid=holder["pid"]))
            return 0
    left = _stop_all([h["pid"] for h in found])
    if left:
        _output(context=messages.ctx("stuck", name=name, pid=left[0]))
    else:
        _output(title=name)
    return 0
