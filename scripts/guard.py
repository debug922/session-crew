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
import registry
import repos
import shellwords as sw
import size

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREW = os.path.join(ROOT, "scripts", "crew.py")
_PATH = "|".join(re.escape(p) for p in sorted({CREW, os.path.realpath(CREW)}))
DOOR = re.compile(r"python3 -I (?:\"(?:%s)\"|'(?:%s)'|(?:%s)) (?:push ([A-Za-z0-9][\w.-]*)"
                  r"|tag ([A-Za-z0-9][\w.-]*) (v\d+\.\d+\.\d+))" % (_PATH, _PATH, _PATH))
DOOR_WORDS = re.compile(r"crew\.py[\"']?\s+(?:push|tag)\b")
APPLY_WORDS = re.compile(r"crew\.py[\"']?\s+config\s+apply\b")
RAW_DOOR = re.compile(r"crew\.py\W+(?:push|tag|config)\b")  # in the event's JSON text, for a crash
PROJECT_FILE = re.compile(r"\.session-crew/[^/\s'\"]+/project\.json")
WRITERS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}
NIGHT = (" A night is on and nobody is here to confirm, so this is refused instead of waiting until "
         "morning: leave it, or park the item and put the question in the report.")
CONFIG_ASK = ("This writes session-crew's configuration (the project file, which decides who pushes "
              "what, or the plugin's own folder). It runs only if the user confirms.")


def find_project(event):
    """The folder whose project governs this event: the event's, else the session's own."""
    cwd = event.get("cwd") or os.getcwd()
    entry = registry.find_by_session_id(event.get("session_id")) if event.get("session_id") else None
    for c in (cwd, (entry or {}).get("cwd")):
        found = config.locate(c) if c else None
        if found:
            return found
    return None


def session_name(event):
    """The name the user gave this session, from the registry; None when it has none of his."""
    entry = registry.find_by_session_id(event.get("session_id")) if event.get("session_id") else None
    return entry.get("name") if entry and entry.get("nameSource") == "user" else None


class Verdict:
    def __init__(self, kind, reason):
        self.kind, self.reason = kind, reason


def settle(verdict, pcwd):
    """An ask becomes a deny while a night is on."""
    if verdict and verdict.kind == "ask" and size.unattended_active(config.load_project(pcwd)):
        return Verdict("deny", verdict.reason + NIGHT)
    return verdict


def toplevel(start):
    """The repository holding start (a worktree counts as its main repository), or None."""
    d = os.path.realpath(start)
    while True:
        dot = os.path.join(d, ".git")
        if os.path.isdir(dot):
            return d
        if os.path.isfile(dot):
            try:
                with open(dot, encoding="utf-8") as f:
                    gitdir = f.read().strip().partition("gitdir:")[2].strip()
            except OSError:
                return None
            gitdir = os.path.normpath(os.path.join(d, gitdir))
            return os.path.dirname(gitdir.split(os.sep + "worktrees" + os.sep)[0]) \
                if os.sep + "worktrees" + os.sep in gitdir else d
        if os.path.dirname(d) == d:
            return None
        d = os.path.dirname(d)


def names_repo(table, top):
    """True when the table names the repository at top (a table that cannot be read names all)."""
    if table.entries is None or top is None:
        return True
    return any(os.path.realpath(e["path"]) == top for e in table.entries.values())


def where(toks, opts, cwd):
    """The repository a git call acts on, or None when it cannot be told (a cd, --git-dir)."""
    if any(os.path.basename(t) in ("cd", "pushd") for t in toks):
        return None
    start = sw.git_start_dir(opts, cwd)
    return toplevel(start) if start else None


def door(line, event, table):
    m = DOOR.fullmatch(line)
    if not m:
        return Verdict("deny", "The door runs only as `python3 -I <plugin>/scripts/crew.py push <repo>` "
                               "or `... tag <repo> vX.Y.Z`, by the plugin's own path, alone on its "
                               "line (/push and /release write it).")
    if event.get("agent_id"):
        return Verdict("deny", "The door pushes and tags for a session itself, never for one of its "
                               "agents: the agent reports, the session releases.")
    repo, tagged = m.group(1) or m.group(2), m.group(3)
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


def configuration(named, pcwd):
    """Words that run `config apply` or write the project file or the plugin's folder."""
    if APPLY_WORDS.search(named):
        return Verdict("ask", "`config apply` writes the project file, which decides who pushes "
                              "what. It runs only if the user confirms.")
    mine = [PROJECT_FILE.pattern] + [re.escape(p) for p in
                                     (config.project_file(pcwd), ROOT, os.path.realpath(ROOT))]
    return Verdict("ask", CONFIG_ASK) if sw.writes_to(named, mine) else None


def git_rules(toks, cwd, table):
    for sub, args, opts in sw.git_calls(toks):
        top = where(toks, opts, cwd)
        outside = top is not None and not names_repo(table, top)
        if sub == "push":
            if sw.push_deletes(args):
                return Verdict("ask", "This push deletes or rewrites on the remote (--force, --delete, "
                                      "a refspec with + or :, --mirror, --prune), which goes only on "
                                      "the user's explicit request. It runs only if he confirms.")
            if table.active and not outside:
                return Verdict("deny", "git push runs through the door in this project: use /push "
                                       "<repo> (crew.py push). A repository outside the project's "
                                       "table is pushed from inside that repository, without cd.")
        if sub == "tag" and table.active and sw.tag_writes(args) and not outside:
            return Verdict("deny", "A tag is made through the door (/release <repo> vX.Y.Z) for a "
                                   "repository the table gives tags, and never moved or deleted; "
                                   "listing tags (git tag -l) is allowed.")
    return None


def repo_flag(toks):
    """The owner/name given to gh with -R or --repo, lowered, or None."""
    for i, t in enumerate(toks[:-1]):
        if t in ("-R", "--repo"):
            return toks[i + 1].lower()
    return None


def gh_release(toks, cwd, table):
    """`gh release create` makes a tag: refused for a repository of the table (or one not told)."""
    for i, tok in enumerate(toks):
        if os.path.basename(tok) != "gh" or toks[i + 1:i + 3] != ["release", "create"] \
                or not table.active:
            continue
        flag = repo_flag(toks)
        if flag and table.entries is not None:
            named = flag in {e["github"].lower() for e in table.entries.values()}
        else:
            top = where(toks, [], cwd)
            named = top is None or names_repo(table, top)
        if named:
            return Verdict("deny", "gh release create makes a tag: tags go through the door "
                                   "(/release <repo> vX.Y.Z).")
    return None


def check_bash(event):
    pcwd = find_project(event)
    if pcwd is None or event.get("tool_name") != "Bash":
        return None
    cmd = (event.get("tool_input") or {}).get("command") or ""
    cwd = event.get("cwd") or os.getcwd()
    toks = sw.tokens(cmd)
    named = " ".join(sw.without_messages(toks))
    table = repos.read(pcwd)
    if DOOR_WORDS.search(named):
        return settle(door(cmd.strip(), event, table), pcwd)
    for found in (configuration(named, pcwd),
                  Verdict("ask", "This deletes something on GitHub, which goes only on the user's "
                                 "explicit request. It runs only if he confirms.")
                  if sw.github_deletes(cmd, toks) else None,
                  git_rules(toks, cwd, table), gh_release(toks, cwd, table)):
        if found:
            return settle(found, pcwd)
    return None


def norm(path, cwd):
    path = os.path.expanduser(path)
    return os.path.realpath(path if os.path.isabs(path) else os.path.join(cwd, path)).lower()


def check_files(event):
    pcwd = find_project(event)
    if pcwd is None or event.get("tool_name") not in WRITERS:
        return None
    ti = event.get("tool_input") or {}
    raw = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
    if not raw:
        return None
    path = norm(raw, event.get("cwd") or os.getcwd())
    crew = os.path.realpath(config.home()).lower()
    plugin = os.path.realpath(ROOT).lower()
    ours = (os.path.basename(path) == "project.json" and os.path.dirname(os.path.dirname(path)) == crew) \
        or path == plugin or path.startswith(plugin + os.sep)
    return settle(Verdict("ask", CONFIG_ASK), pcwd) if ours else None


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
