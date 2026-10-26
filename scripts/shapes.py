"""The exact shapes of a command line that reaches the plugin's scripts.

A line is held to these shapes when a word lies under the installed plugin's folder (or is a glob
that could match one there), or when it executes a script named crew.py (or a glob that could
match one). Then it must be exactly one shape, judged on the whole line: alone, no env prefix, no
`bash -c`, no `$(...)`, no extra words; or the guard refuses it. A crew.py that is only an argument
of git, grep or an editor is not run, and a plain read (cat, grep, ls ...) of the plugin is free.
"""
import fnmatch
import os
import re
import shlex

from shellwords import SHELLS, _has_c, tokens

SAFE = re.compile(r"[\w./~+@%:-]+")
REPO = re.compile(r"[A-Za-z0-9][\w.-]*")
VERSION = re.compile(r"v\d+\.\d+\.\d+")
FLAGS = ("--name", "--session-id", "--cwd")
HOOKS = {"size", "rename", "start", "guard-bash", "guard-files"}
READERS = {"cat", "ls", "grep", "egrep", "fgrep", "rg", "head", "tail", "wc", "stat", "file", "less",
           "diff", "jq", "nl", "tree"}
HEREDOC_TAIL = re.compile(r"\s<<\s*(['\"])(\w+)\1\s*$")
ALLOWED = ("The allowed shapes, each alone on its line, by the plugin's own path "
           "(python3 -I \"<plugin>/scripts/crew.py\" ...): push <repo>; tag <repo> vX.Y.Z; "
           "config show|discover [--cwd DIR]; config apply DRAFT [--cwd DIR]; "
           "handoff save|status; migrate [name]; recover [target]; size [path] (those four with "
           "--name, --session-id, --cwd); hook size|rename|start. No env prefix, no bash -c, "
           "no $(...), no extra words.")


class Shape:
    def __init__(self, kind, repo=None, version=None):
        self.kind, self.repo, self.version = kind, repo, version


def _flags_ok(args):
    """True when args are only `--name|--session-id|--cwd VALUE` pairs."""
    return len(args) % 2 == 0 and all(
        args[i] in FLAGS and SAFE.fullmatch(args[i + 1]) for i in range(0, len(args), 2))


def _with_one_positional(args):
    """True when args are flag pairs and at most one positional word, in any order."""
    rest, i, positional = [], 0, 0
    while i < len(args):
        if args[i] in FLAGS:
            rest += args[i:i + 2]
            i += 2
        else:
            positional += 1
            i += 1
    return positional <= 1 and _flags_ok(rest) and all(
        SAFE.fullmatch(a) for a in args if a not in FLAGS)


def _apply_ok(args):
    """DRAFT, with an optional --cwd DIR before or after it."""
    if len(args) == 1:
        return bool(SAFE.fullmatch(args[0])) and args[0] != "--cwd"
    if len(args) == 3 and args[1] == "--cwd":
        return bool(SAFE.fullmatch(args[0])) and args[0] != "--cwd" and bool(SAFE.fullmatch(args[2]))
    if len(args) == 3 and args[0] == "--cwd":
        return bool(SAFE.fullmatch(args[1])) and bool(SAFE.fullmatch(args[2])) and args[2] != "--cwd"
    return False


def _sub(sub, args, heredoc):
    if sub == "push":
        return Shape("door", args[0]) if len(args) == 1 and REPO.fullmatch(args[0]) and not heredoc else None
    if sub == "tag":
        ok = len(args) == 2 and REPO.fullmatch(args[0]) and VERSION.fullmatch(args[1])
        return Shape("door", args[0], args[1]) if ok and not heredoc else None
    if heredoc and not (sub == "handoff" and args[:1] == ["save"]):
        return None
    if sub == "config" and args[:1] in (["show"], ["discover"]):
        return Shape("safe") if args[1:] == [] or (args[1] == "--cwd" and _flags_ok(args[1:])) else None
    if sub == "config" and args[:1] == ["apply"]:
        return Shape("apply") if _apply_ok(args[1:]) else None
    if sub == "handoff" and args[:1] in (["save"], ["status"]):
        return Shape("safe") if _flags_ok(args[1:]) else None
    if sub in ("migrate", "recover", "size"):
        return Shape("safe") if _with_one_positional(args) else None
    if sub == "hook":
        return Shape("safe") if len(args) == 1 and args[0] in HOOKS else None
    return None


def classify(cmd, paths):
    """The Shape of a whole command line, or None when it is not exactly an allowed one."""
    first, _, rest = cmd.strip().partition("\n")
    heredoc = bool(rest)
    if heredoc:
        m = HEREDOC_TAIL.search(first)
        lines = rest.rstrip("\n").split("\n")
        if not m or lines[-1] != m.group(2) or m.group(2) in lines[:-1]:
            return None
        first = first[:m.start()]
    try:
        toks = shlex.split(first)
    except ValueError:
        return None
    if len(toks) < 4 or toks[:2] != ["python3", "-I"]:
        return None
    installed = toks[2] in paths
    if not installed and os.path.basename(toks[2]) != "crew.py":
        return None
    if not (installed or SAFE.fullmatch(toks[2])) or any(not SAFE.fullmatch(a) for a in toks[3:]):
        return None
    shape = _sub(toks[3], toks[4:], heredoc)
    # Another crew.py (a checkout, a copy) runs v1's shapes and config reads, never the door or apply.
    return shape if shape and (installed or shape.kind == "safe") else None


def _under(path, folders):
    return any(path == d or path.startswith(d + os.sep) for d in folders)


def names_plugin(toks, cwd, folders):
    """(a) True when a word lies under the installed plugin's folder (resolved from cwd, symlinks
    too), or is a glob that could match something there: copying a script out still names it."""
    cands = []
    for d in folders:
        try:
            cands += [d] + [os.path.join(d, f) for f in os.listdir(d)]
            cands += [os.path.join(d, "scripts", f) for f in os.listdir(os.path.join(d, "scripts"))]
        except OSError:
            pass
    for t in toks:
        if any(d in t for d in folders):
            return True
        if t.startswith("-") or set(t) <= set(";&|()"):
            continue
        full = os.path.normpath(os.path.join(cwd, os.path.expanduser(t)))
        if _under(full, folders) or _under(os.path.realpath(full), folders):
            return True
        if any(c in t for c in "*?[") and any(fnmatch.fnmatchcase(c, full) for c in cands):
            return True
    return False


def is_crew(word):
    """A script named crew.py, or a glob whose last part could match that name."""
    base = os.path.basename(word)
    return base == "crew.py" or (any(c in base for c in "*?[") and fnmatch.fnmatchcase("crew.py", base))


WRAPPERS = {"env", "nice", "sudo", "time", "exec", "command", "nohup", "xargs"}
PYTHON = re.compile(r"python[\d.]*")


def _script_of_python(toks, j):
    """The script a python at toks[j] runs, or None (-c and -m run no file)."""
    for k in range(j + 1, len(toks)):
        t = toks[k]
        if t.startswith("-"):
            if not t.startswith("--") and set("cm") & set(t[1:]):
                return None
            continue
        return t
    return None


def runs_crew(toks, cwd, depth=0):
    """(b) True when a simple command executes a script named crew.py (or a glob that could match
    one): the program word itself, or the script argument of python, also inside `sh -c`, `eval`.
    A crew.py that is only an argument of git, grep, cat or an editor is not run."""
    for i, t in enumerate(toks):
        if i and not set(toks[i - 1]) <= set(";&|("):
            continue
        j = i
        while j < len(toks) and ("=" in toks[j] and not toks[j].startswith("-")
                                 or os.path.basename(toks[j]) in WRAPPERS):
            j += 1
        if j >= len(toks):
            continue
        prog, base = toks[j], os.path.basename(toks[j])
        if is_crew(prog):
            return True
        if PYTHON.fullmatch(base):
            script = _script_of_python(toks, j)
            if script and is_crew(script):
                return True
        elif base in SHELLS and depth < 3:
            rest = toks[j + 1:]
            if rest and _has_c(rest[0]) and len(rest) > 1:
                if runs_crew(tokens(rest[1]), cwd, depth + 1):
                    return True
            elif rest and not rest[0].startswith("-") and is_crew(rest[0]):
                return True
        elif base == "eval" and depth < 3 and runs_crew(tokens(" ".join(toks[j + 1:])), cwd, depth + 1):
            return True
        elif base in ("source", ".") and len(toks) > j + 1 and is_crew(toks[j + 1]):
            return True
    return False


def reader_only(toks, cmd):
    """A plain read (cat, grep, ls ...): no operators, no substitution."""
    return bool(toks) and os.path.basename(toks[0]) in READERS \
        and not any(set(t) <= set(";&|()") for t in toks) and "`" not in cmd and "$(" not in cmd
