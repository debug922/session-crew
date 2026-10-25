"""`crew.py config show|discover|apply`: the project file made and changed in chat (section 11.3)."""
import json
import os
import sys

import config
import gitrun
import project
import registry
import repos

SKIP = {"node_modules", "vendor"}
LACKS = (("repos", "no repositories are linked: the git flow is idle"),
         ("commit_rules", "no rules for the commits' messages"),
         ("sessions", "no sessions named: /migrate prints no role"))


def project_cwd(ident):
    """The folder whose project this is: the nearest one with a project.json, else the session's."""
    return config.locate(ident.cwd) or ident.cwd


def show(ident):
    cwd = project_cwd(ident)
    path = config.project_file(cwd)
    if not os.path.isfile(path):
        print("%s: no project file yet (%s). /setup makes one." % (cwd, path))
        return 0
    data = project.read_current(cwd)
    print("%s\n%s" % (path, json.dumps(data, indent=2, sort_keys=True)))
    errors, warnings = project.validate(data)
    for line in errors + warnings:
        print("problem: " + line)
    for key, why in LACKS:
        if not data.get(key):
            print("lacks %s: %s" % (key, why))
    return 0


def repo_dirs(folder):
    """Folders with a .git, the folder itself and two levels below it; a repository is not entered."""
    found, level = [], [folder]
    for depth in range(3):
        nxt = []
        for d in level:
            if os.path.exists(os.path.join(d, ".git")):
                found.append(d)
            elif depth < 2:
                try:
                    kids = sorted(e.path for e in os.scandir(d) if e.is_dir(follow_symlinks=False)
                                  and not e.name.startswith(".") and e.name not in SKIP)
                except OSError:
                    kids = []
                nxt += kids
        level = nxt
    return found


def describe(path, table_names):
    origin = gitrun.git(path, "remote", "get-url", "origin", check=False) or None
    github = repos.github_of(origin)
    real = os.path.realpath(path)
    return {"path": path, "origin": origin, "github": github,
            "visibility": repos.visibility_of(github) if github else None,
            "in_table": table_names.get(real)}


def named_sessions(folder):
    """The sessions the user named in this folder (a derived name is not his), live ones first."""
    best = {}
    for e in registry.read_all():
        if e.get("cwd") != folder or e.get("nameSource") != "user" or not e.get("name"):
            continue
        alive = type(e.get("pid")) is int and e["pid"] > 1 and registry.pid_alive(e["pid"])
        best[e["name"]] = best.get(e["name"], False) or alive
    return [{"name": n, "alive": a} for n, a in sorted(best.items(), key=lambda kv: (not kv[1], kv[0]))]


def discover(ident):
    cwd = project_cwd(ident)
    current = project.read_current(cwd)
    table = repos.read(cwd).entries or {}
    names = {os.path.realpath(e["path"]): n for n, e in table.items()}
    paths = repo_dirs(cwd)
    seen = {os.path.realpath(p) for p in paths}
    paths += [e["path"] for e in table.values()
              if os.path.realpath(e["path"]) not in seen and os.path.isdir(e["path"])]
    out = {"folder": cwd, "file": config.project_file(cwd), "drafts_dir": project.drafts_dir(cwd),
           "current": current or None, "sessions": named_sessions(cwd),
           "repos_found": [describe(p, names) for p in paths]}
    print(json.dumps(out, indent=2))
    return 0


def confirmed(ask, tty):
    """A typed yes counts only from a terminal: a session can pipe `yes` into a script."""
    return ask("Type yes to write this file: ").strip().lower() == "yes"


def apply(ident, draft, ask=input, tty=lambda: os.isatty(0)):
    """Validate a draft, print what changes, keep the previous file, write the new one.

    Under Claude Code (a session in the registry) the guard has asked the user before this runs.
    Elsewhere (Copilot) there is no guard to stand between the session and the write, so the
    script asks for a typed yes itself (V8)."""
    cwd = project_cwd(ident)
    try:
        data = project.read_draft(cwd, draft)
    except ValueError as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 1
    errors, warnings = project.validate(data)
    if errors:
        print("refused: the draft is not a project file:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    lines = project.diff(project.read_current(cwd), data)
    for w in warnings:
        print("warning: " + w)
    if not lines:
        print("nothing changes: the draft is the file as it is")
        return 0
    print("changes:\n  " + "\n  ".join(lines))
    if ident.session_id is None:
        if not tty():
            print("refused: outside Claude Code nothing guards this write, so it is made only from "
                  "a terminal (stdin is not one here). Run this line in your own terminal:\n  "
                  "python3 -I %s config apply %s --cwd %s"
                  % (os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew.py"), draft, cwd),
                  file=sys.stderr)
            return 1
        if not confirmed(ask, tty):
            print("nothing written")
            return 1
    project.write(cwd, data)
    print("written: %s (the previous file is project.json.prev)" % config.project_file(cwd))
    return 0
