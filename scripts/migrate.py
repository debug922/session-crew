"""`migrate` and the SessionStart hook."""
import json
import os
import sys

import config
import handoff
import messages
import recover
import registry
import size


def hook_start(event):
    if event.get("source") not in ("startup", "clear"):
        return 0
    ident = registry.from_event(event)
    cfg = config.load_project(ident.cwd)
    if ident.name:
        found = handoff.latest_pending(ident.cwd, ident.handoff_name)
        cmd = "/migrate"
    else:
        found = handoff.latest_pending(ident.cwd)
        cmd = "/migrate " + found[1].get("name", "") if found else "/migrate"
    if not found:
        return 0
    name = found[1].get("name", ident.handoff_name)
    size.emit("SessionStart", messages.ctx("waiting", name=name, cmd=cmd),
              messages.user(cfg["lang"], "waiting", name=name, cmd=cmd))
    return 0


def _holder_note(holder):
    path = os.path.join(config.claude_dir(), "projects", config.slug(holder.get("cwd", "")),
                        "%s.jsonl" % holder.get("sessionId"))
    return "NOTE: a live session called %s holds this name in this folder: pid %s, status %s, " \
           "transcript %.0f MB." % (holder.get("name"), holder["pid"], holder.get("status"),
                                    size.size_mb(path))


def run(ident, name):
    if not name and not ident.name:
        found = handoff.latest_pending(ident.cwd)
        name = found[1].get("name") if found else None
    name = name or ident.handoff_name
    for holder in registry.holders(name, ident.cwd, ident.session_id):
        print(_holder_note(holder) + "\n")
    found = handoff.latest_pending(ident.cwd, config.safe_name(name))
    if not found:
        print("No pending handoff for %s; recovering from the old transcript.\n" % name)
        return recover.run(ident, name)
    path, meta = found
    _, body = handoff.parse(path)
    print("# Handoff %s (written %s)\n" % (os.path.basename(path), meta.get("written_at", "")))
    print(body)
    entry = _project_entry(ident.cwd, name)
    if entry:
        print("\n# This session in project.json\n")
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    handoff.mark_used(path, ident.session_id)
    return 0


def _project_entry(cwd, name):
    for s in config.load_project(cwd).get("sessions", []):
        if isinstance(s, dict) and s.get("name") == name:
            return s
    return None
