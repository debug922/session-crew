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
import registry
import repos
import shapes
import shellwords as sw
import size
from verdict import Verdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREW = os.path.join(ROOT, "scripts", "crew.py")
CREW_PATHS = {CREW, os.path.realpath(CREW)}
SCRIPTS = sorted({os.path.dirname(p) for p in CREW_PATHS})
APPLY_WORDS = re.compile(r"crew\.py[\"']?\s+config\s+apply\b")
RAW_DOOR = re.compile(r"crew\.py\W+(?:push|tag|config)\b")  # in the event's JSON text, for a crash
CREW_HOME = r"\.session-crew"
INTERPRETER = re.compile(r"(?:python[\d.]*|perl|ruby|node)")
INLINE_FLAG = re.compile(r"-[A-Za-z]*[ceE]")
WRITERS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
NIGHT = (" A night is on and nobody is here to confirm, so this is refused instead of waiting until "
         "morning: leave it, or park the item and put the question in the report.")
CONFIG_ASK = ("This writes session-crew's configuration (the project file, which decides who pushes "
              "what, or the plugin's own folder). It runs only if the user confirms.")


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


def inline_code(toks):
    """The code strings given to an interpreter with -c or -e (python, perl, ruby, node)."""
    for i, t in enumerate(toks):
        if not INTERPRETER.fullmatch(os.path.basename(t)):
            continue
        for k in range(i + 1, len(toks)):
            if set(toks[k]) <= set(";&|()"):
                break
            if INLINE_FLAG.fullmatch(toks[k]) and k + 1 < len(toks):
                yield toks[k + 1]
                break


def configuration(named, toks, pcwd):
    """Words that run `config apply`, or write (a verb or a redirection) anything under the crew
    home or the plugin's folder, or hand an interpreter inline code that names them."""
    if APPLY_WORDS.search(named):
        return Verdict("ask", "`config apply` writes the project file, which decides who pushes "
                              "what. It runs only if the user confirms.")
    mine = [CREW_HOME, re.escape(config.home())] + [re.escape(p) for p in {ROOT, os.path.realpath(ROOT)}]
    if sw.writes_to(named, mine) or any(re.search(p, c) for c in inline_code(toks) for p in mine):
        return Verdict("ask", CONFIG_ASK)
    return None


def crew_shape(cmd, toks, named_toks, cwd, event, pcwd):
    """The verdict for a line that names the plugin's scripts: (decided, verdict). Only a
    configured project is held to the exact shapes; elsewhere only `config apply` is asked about
    (by configuration)."""
    if pcwd is None or not shapes.names_scripts(named_toks, cwd, SCRIPTS):
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
    decided, verdict = crew_shape(cmd, toks, named_toks, cwd, event, pcwd)
    if decided:
        return verdict
    found = configuration(named, named_toks, pcwd)
    if found:
        return settle(found, pcwd)
    if pcwd is None:
        return None
    table = repos.read(pcwd)
    for found in (Verdict("ask", "This deletes something on GitHub, which goes only on the user's "
                                 "explicit request. It runs only if he confirms.")
                  if sw.github_deletes(cmd, toks) else None,
                  gitguard.git_rules(toks, cwd, table), gitguard.gh_release(toks, cwd, table)):
        if found:
            return settle(found, pcwd)
    return None


def norm(path, cwd):
    path = os.path.expanduser(path)
    return os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path)).lower()


def lexical(path, cwd):
    """The path as written, ~ and .. resolved, no symlink followed."""
    path = os.path.expanduser(path)
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path)).lower()


def check_files(event):
    if event.get("tool_name") not in WRITERS:
        return None
    pcwd = find_project(event)
    ti = event.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    if not raw:
        return None
    cwd = event.get("cwd") or os.getcwd()
    homes = [os.path.normpath(config.home()).lower(), os.path.realpath(config.home()).lower()]
    plugins = [os.path.normpath(ROOT).lower(), os.path.realpath(ROOT).lower()]
    # Either spelling counts: a symlinked folder pointing out of the home, or one pointing in.
    for path in (lexical(raw, cwd), os.path.realpath(os.path.join(cwd, os.path.expanduser(raw))).lower()):
        in_home = os.path.basename(path) == "project.json" and any(path.startswith(h + os.sep) for h in homes)
        in_plugin = any(path == d or path.startswith(d + os.sep) for d in plugins)
        if in_home or in_plugin:
            return settle(Verdict("ask", CONFIG_ASK), pcwd)
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
