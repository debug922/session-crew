"""The git rules of the Bash guard: where a git call acts, and what a push or a tag may do."""
import os
import re
import shlex

import pushdest
import remotes
import shellwords as sw
from verdict import Verdict


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


KNOWN = {"push", "tag", "commit", "status", "log", "diff", "add", "checkout", "fetch", "pull", "merge",
         "rebase", "branch", "show", "clone", "init", "remote", "config", "worktree", "stash", "reset",
         "cherry-pick", "rev-parse", "ls-remote", "describe", "switch", "restore", "rm", "mv", "apply",
         "am", "bisect", "blame", "grep", "clean", "gc", "notes", "submodule", "archive", "revert"}
PUSH_OR_TAG = re.compile(r"\b(?:push|tag|pushd|popd|cd)\b|!")
CONFIG_KEYS = re.compile(r"(?:alias|url|remote)\.", re.IGNORECASE)
GIT_ENV = re.compile(r"GIT_\w+=")


def _env_moves(args):
    """True when the words after `env` change its folder (-C, --chdir)."""
    for a in args:
        if a in ("-C", "--chdir") or a.startswith("--chdir=") or (a.startswith("-C") and len(a) > 2):
            return True
        if not a.startswith("-") and "=" not in a:
            return False
    return False


def blind(lists):
    """True when a call's place cannot be told from the words: a cd, pushd or popd, an env prefix
    such as GIT_DIR, env -C, find -exec running git, or ssh, in any of the command's lines."""
    for toks in lists:
        for i, t in enumerate(toks):
            base = os.path.basename(t)
            rest = toks[i + 1:]
            if base in ("cd", "pushd", "popd") or GIT_ENV.match(t):
                return True
            if base == "env" and _env_moves(rest):
                return True
            if base == "find" and any(a in ("-exec", "-execdir", "-ok", "-okdir") for a in rest) \
                    and any(os.path.basename(a) == "git" for a in rest):
                return True
            if base == "ssh" and any("git" in a for a in rest):
                return True
    return False


def opaque(toks):
    """True when a program word is a variable or a substitution and push or tag stands beside it:
    the guard cannot tell it is not git."""
    wrapped = ("env", "nice", "sudo", "time", "exec", "command", "nohup")
    for i, t in enumerate(toks):
        start = i == 0 or set(toks[i - 1]) <= set(";&|(") or (
            toks[i - 1] in wrapped or "=" in toks[i - 1] and not toks[i - 1].startswith("-"))
        if start and t.startswith(("$", "`")) and any(a in ("push", "tag") for a in toks[i + 1:]):
            return True
    return False


def place(opts, cwd, lost):
    """The repository a git call acts on, or None when it cannot be told (a cd, an env prefix,
    --git-dir, --work-tree)."""
    start = None if lost else sw.git_start_dir(opts, cwd)
    return toplevel(start) if start else None


def resolve_alias(sub, args, start):
    """(sub, args) with git aliases of the repository expanded, read now; ("!", [shell text]) for
    an alias that runs a shell command."""
    for _ in range(3):
        value = None if sub in KNOWN or not os.path.isdir(start) else pushdest.alias_value(start, sub)
        if not value:
            break
        if value.startswith("!"):
            return "!", [value[1:]] + args
        try:
            parts = shlex.split(value)
        except ValueError:
            break
        if not parts:
            break
        sub, args = parts[0], parts[1:] + args
    return sub, args


def defines_alias(sub, opts, args):
    """True for `git -c alias.x=...` (or url.*, remote.*) and `git config alias.x <push or tag>`."""
    if any(o == "-c" and i + 1 < len(opts) and CONFIG_KEYS.match(opts[i + 1])
           for i, o in enumerate(opts)):
        return True
    if sub == "config":
        for i, a in enumerate(args):
            if a.lower().startswith("alias.") and (PUSH_OR_TAG.search(" ".join(args[i:])) or "=" in a
                                                    and PUSH_OR_TAG.search(a.partition("=")[2])):
                return True
    return False


def push_verdict(args, top, table, subs):
    """The refusal of a plain push in a configured project, or None when it is provably elsewhere:
    placed, not a table repository, and every place it pushes to a URL that is not a table's."""
    if top is None or names_repo(table, top):
        return Verdict("deny", "git push runs through the door in this project: use /push <repo> "
                               "(crew.py push). A repository outside the project's table is pushed "
                               "from inside that repository, with no cd, env prefix or --git-dir.")
    if "remote" in subs or "config" in subs:
        return Verdict("deny", "This line changes remotes or configuration and pushes: the guard "
                               "cannot tell where the push goes. Do them in separate commands.")
    urls = pushdest.destinations(top, args)
    if not urls:
        return Verdict("deny", "The guard cannot resolve where this push goes (a remote that is not "
                               "in the repository's configuration).")
    mine = {e["github"].lower() for e in table.entries.values()}
    kinds = [remotes.parse(u) for u in urls]
    if any(kind == "bad" for kind, _ in kinds):
        return Verdict("deny", "This push goes to a URL that names GitHub but not one repository the "
                               "guard can read: refused, since it could be a table repository.")
    if any(name in mine for _, name in kinds):
        return Verdict("deny", "This push goes to a repository of the project's table: use /push "
                               "<repo> (crew.py push).")
    return None


def git_rules(toks, cwd, table, lost, depth=0):
    if table.active and opaque(toks):
        return Verdict("deny", "The program here is a variable or a substitution beside push or tag: "
                               "the guard cannot tell it is not git. Write git itself.")
    calls = list(sw.git_calls(toks))
    subs = [c[0] for c in calls]
    for sub, args, opts in calls:
        if defines_alias(sub, opts, args):
            return Verdict("deny", "This defines a git alias, a url rewrite or a remote through -c or "
                                   "git config in a way that could hide a push or a tag. Run git "
                                   "push and git tag as themselves, through the door.")
        start = sw.git_start_dir(opts, cwd) or cwd
        sub, args = resolve_alias(sub, args, start)
        if sub == "!":
            lists = sw.all_lists(args[0]) if depth < 3 else []
            for inner in lists:
                found = git_rules(inner, cwd, table, lost or blind(lists), depth + 1)
                if found:
                    return found
            continue
        top = place(opts, cwd, lost)
        if sub == "push":
            if sw.push_deletes(args):
                return Verdict("ask", "This push deletes or rewrites on the remote (--force, --delete, "
                                      "a refspec with + or :, --mirror, --prune), which goes only on "
                                      "the user's explicit request. It runs only if he confirms.")
            if table.active:
                found = push_verdict(args, top, table, subs)
                if found:
                    return found
        if sub == "tag" and table.active and sw.tag_writes(args) \
                and (top is None or names_repo(table, top)):
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


def gh_release(toks, cwd, table, lost):
    """`gh release create` makes a tag: refused for a repository of the table (or one not told)."""
    for i, tok in enumerate(toks):
        if os.path.basename(tok) != "gh" or toks[i + 1:i + 3] != ["release", "create"] \
                or not table.active:
            continue
        flag = repo_flag(toks)
        if flag and table.entries is not None:
            named = flag in {e["github"].lower() for e in table.entries.values()}
        else:
            top = place([], cwd, lost)
            named = top is None or names_repo(table, top)
        if named:
            return Verdict("deny", "gh release create makes a tag: tags go through the door "
                                   "(/release <repo> vX.Y.Z).")
    return None
