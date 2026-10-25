"""The exact shapes of a command line that names the plugin's scripts.

Anything that names crew.py, a word under the plugin's scripts folder, or a glob that could match
one there, must be exactly one of these shapes (judged on the whole line, alone, no env prefix, no
`bash -c`, no `$(...)`, no extra words), or the guard refuses it. Reading the scripts with a
plain reader (cat, grep, ls ...) is free.
"""
import fnmatch
import os
import re
import shlex

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
    if sub == "config" and args[:1] == ["apply"] and len(args) >= 2 and SAFE.fullmatch(args[1]):
        return Shape("apply") if args[2:] == [] or (args[2] == "--cwd" and _flags_ok(args[2:])) else None
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
    if len(toks) < 4 or toks[:2] != ["python3", "-I"] or toks[2] not in paths:
        return None
    if any(not SAFE.fullmatch(a) for a in toks[3:]):
        return None
    return _sub(toks[3], toks[4:], heredoc)


def _under(path, folders):
    return any(path == d or path.startswith(d + os.sep) for d in folders)


def names_scripts(toks, cwd, folders):
    """True when a word is crew.py, lies under the scripts folder (resolved from cwd), or is a glob
    that could match something there."""
    cands = []
    for d in folders:
        try:
            cands += [d] + [os.path.join(d, f) for f in os.listdir(d)]
        except OSError:
            pass
    for t in toks:
        if "crew.py" in t or any(d in t for d in folders):
            return True
        if t.startswith("-") or set(t) <= set(";&|()"):
            continue
        full = os.path.normpath(os.path.join(cwd, os.path.expanduser(t)))
        if _under(full, folders) or _under(os.path.realpath(full), folders):
            return True
        if any(c in t for c in "*?[") and any(fnmatch.fnmatchcase(c, full) for c in cands):
            return True
    return False


def reader_only(toks, cmd):
    """A plain read (cat, grep, ls ...): no operators, no substitution."""
    return bool(toks) and os.path.basename(toks[0]) in READERS \
        and not any(set(t) <= set(";&|()") for t in toks) and "`" not in cmd and "$(" not in cmd
