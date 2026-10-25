"""The git rules of the Bash guard: where a git call acts, and what a push or a tag may do."""
import os

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


def where(toks, opts, cwd):
    """The repository a git call acts on, or None when it cannot be told (a cd, --git-dir)."""
    if any(os.path.basename(t) in ("cd", "pushd") for t in toks):
        return None
    start = sw.git_start_dir(opts, cwd)
    return toplevel(start) if start else None


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
