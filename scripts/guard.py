"""The PreToolUse guards (section 11.6) for the Bash tool and the file tools.

They act for the project of the event's folder (config.locate) and say nothing where there is none:
the flow is the project's, never global. They read the project file and the registry, never the
network. Answers are permissionDecision JSON; deny wins over ask whichever hook says it. While a
night is on (the project's unattended status command) every ask is a deny.
"""
import json
import os
import re
import sys

import config
import gitguard
import protect
import registry
import repos
import shapes
import shellwords as sw
import size
from verdict import Verdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREW = os.path.join(ROOT, "scripts", "crew.py")
CREW_PATHS = {CREW, os.path.realpath(CREW)}
PLUGIN = sorted({ROOT, os.path.realpath(ROOT)})
RAW_DOOR = re.compile(r"crew\.py\W+(?:push|tag|config)\b")  # in the event's JSON text, for a crash
WRITERS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
NIGHT = (" A night is on and nobody is here to confirm, so this is refused instead of waiting until "
         "morning: leave it, or park the item and put the question in the report.")


def find_project(event):
    """The folder whose project governs this event: the event's own, as the door finds its own
    from the process's folder (never the registry's, so the two agree)."""
    return config.locate(event.get("cwd") or os.getcwd())


def session_name(event):
    """The name the user gave this session, from the registry; None when it has none of his."""
    entry = registry.find_by_session_id(event.get("session_id")) if event.get("session_id") else None
    return entry.get("name") if entry and entry.get("nameSource") == "user" else None


def settle(verdict, pcwd):
    """An ask becomes a deny while a night is on."""
    if verdict and verdict.kind == "ask" and pcwd \
            and size.unattended_active(config.load_project(pcwd)):
        return Verdict("deny", verdict.reason + NIGHT)
    return verdict


def door(shape, event, table):
    if event.get("agent_id"):
        return Verdict("deny", "The door pushes and tags for a session itself, never for one of its "
                               "agents: the agent reports, the session releases.")
    repo, tagged = shape.repo, shape.version
    if table.entries is None:
        return Verdict("deny", "The door opens only for a repository of the project's table, and the "
                               "table could not be read (%s)." % table.error)
    entry = table.entries.get(repo)
    if entry is None:
        return Verdict("deny", "%s is not in the project's table of repositories (%s): its pushes are "
                               "the user's. Commit locally and say what is ready."
                       % (repo, ", ".join(table.entries) or "empty"))
    name = session_name(event)
    if name not in entry["pushers"]:
        return Verdict("deny", "%s is pushed by %s; this session is %s. Tell the session that pushes it "
                               "what is ready." % (repo, ", ".join(entry["pushers"]) or "the user alone",
                                                   name or "not named by him"))
    if tagged and not entry["tags"]:
        return Verdict("deny", "%s's tags are the user's: the table gives it none." % repo)
    if entry["visibility"] == "public":
        return Verdict("ask", "%s is public on GitHub: a push goes out only after the user's ok. It "
                              "runs only if he confirms." % repo)
    return None


def crew_shape(cmd, toks, texts, cwd, event, pcwd):
    """The verdict for a line that names the plugin's scripts: (decided, verdict). Only a
    configured project is held to the exact shapes; elsewhere only `config apply` is asked about
    (by configuration)."""
    # A commit message is text, so the words that name the plugin leave it out; what is run is
    # judged on the whole words (`python -m x` must not lose its argument to the -m rule).
    if pcwd is None or not any(shapes.names_plugin(list(sw.without_messages(t)), cwd, PLUGIN)
                               or shapes.runs_crew(t, cwd) for t in texts):
        return False, None
    shape = shapes.classify(cmd, CREW_PATHS)
    if shape is None:
        if shapes.reader_only(toks, cmd):
            return False, None
        return True, Verdict("deny", "This line names the plugin's scripts but is not one of the "
                                     "allowed shapes. " + shapes.ALLOWED)
    if shape.kind == "door":
        return True, settle(door(shape, event, repos.read(pcwd)), pcwd)
    if shape.kind == "apply":
        return True, settle(Verdict("ask", "`config apply` writes the project file, which decides "
                                           "who pushes what. It runs only if the user confirms."), pcwd)
    return True, None


def check_bash(event):
    """The configuration's protection does not depend on the folder being configured: the file
    that grants pushes is guarded before it exists. The git rules need a project."""
    if event.get("tool_name") != "Bash":
        return None
    pcwd = find_project(event)
    cmd = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or os.getcwd()
    toks = sw.tokens(cmd)
    named_toks = list(sw.without_messages(toks))
    named = " ".join(named_toks)
    texts = sw.all_lists(cmd)
    found = protect.registry_verdict(texts, cwd)  # in every folder, configured or not
    if found:
        return found
    decided, verdict = crew_shape(cmd, toks, texts, cwd, event, pcwd)
    if decided:
        return verdict
    found = protect.configuration(named, texts, cwd, PLUGIN)
    if found:
        return settle(found, pcwd)
    if pcwd is None:
        return None
    table = repos.read(pcwd)
    if table.active:
        found = protect.git_config_edit(texts, cwd)
        if found:
            return found
    lost = gitguard.blind(texts)
    for found in (Verdict("ask", "This deletes something on GitHub, which goes only on the user's "
                                 "explicit request. It runs only if he confirms.")
                  if sw.github_deletes(cmd, toks) else None,
                  *(gitguard.git_rules(t, cwd, table, lost) for t in texts),
                  *(gitguard.gh_release(t, cwd, table, lost) for t in texts)):
        if found:
            return settle(found, pcwd)
    return None


def lexical(path, cwd):
    """The path as written, ~ and .. resolved, no symlink followed."""
    return protect.expand(path, cwd)


def check_files(event):
    if event.get("tool_name") not in WRITERS:
        return None
    pcwd = find_project(event)
    ti = event.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    if not raw:
        return None
    cwd = event.get("cwd") or os.getcwd()
    # Either spelling counts: a symlinked folder pointing out of a protected one, or one pointing in.
    spellings = protect.spellings(lexical(raw, cwd))
    if any(protect.in_sessions(p) for p in spellings):
        return Verdict("deny", "This writes into Claude Code's registry of sessions: never from a tool.")
    plugins = [d.lower() for d in PLUGIN]
    for path in spellings:
        in_home = protect.in_crew_home(path) and not protect.exempt_for_tools(path)
        in_plugin = any(protect.under(path.lower(), d) for d in plugins)
        if in_home or in_plugin:
            return settle(Verdict("ask", protect.CONFIG_ASK), pcwd)
    return None


def emit(verdict):
    if verdict:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": verdict.kind,
            "permissionDecisionReason": verdict.reason}}))


def run(raw, check):
    """A crash on a line naming the door refuses; any other lets the command through (exit 1)."""
    try:
        emit(check(json.loads(raw)))
    except Exception as exc:  # noqa: BLE001
        if RAW_DOOR.search(raw):
            emit(Verdict("deny", "The guard failed (%r) on a command that names the door." % (exc,)))
            return 0
        print("session-crew guard failed open: %r" % (exc,), file=sys.stderr)
        return 1
    return 0


def run_bash(raw):
    return run(raw, check_bash)


def run_files(raw):
    return run(raw, check_files)
