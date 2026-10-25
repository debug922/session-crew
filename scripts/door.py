"""The one door through which a project's sessions push and tag its linked repositories.

  python3 -I <plugin>/scripts/crew.py push <repo>
  python3 -I <plugin>/scripts/crew.py tag <repo> vX.Y.Z

<repo> is a name in the project's table (repos.py). The guard lets this exact line run from a
session the table names among the repository's pushers, never from one of its agents; `git push`
and `git tag` are refused in a configured project. Before anything leaves the machine:

  - main is checked out, origin (fetch and push) is the table's GitHub repository, and main goes
    onto origin/main by fast-forward (never --force);
  - a repository the table calls private is still private on GitHub;
  - the commits to push meet the project's commit_rules;
  - the table's checks pass in a clean worktree of HEAD (checks.py);
  - for a tag, only where the table gives the repository tags: the form vX.Y.Z, the next patch or
    minor of the last tag with the same X (a new X, v1.0.0 included, is the user's), on a line that
    holds the last tag, taken neither here nor on origin, with the version written in the commit
    (CHANGELOG.md's "## vX.Y.Z (" or VERSION, as the table says).

Then it pushes main, makes the tag (lightweight or annotated, as the table says) and pushes it.
Every run lands in ~/.session-crew/<slug>/releases.log. Exit 0 done, 1 refused.
"""
import datetime
import os
import re
import sys

import checks
import config
import repos
import size
from gitrun import Refused, git, is_ancestor

COAUTHOR = re.compile(r"co-authored-by\s*:", re.IGNORECASE)
VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def parse(version):
    m = VERSION.match(version or "")
    return tuple(int(x) for x in m.groups()) if m else None


def why_not_next(last, new):
    """Why new may not follow last, or None when it may. last is None before the first tag."""
    n = parse(new)
    if not n:
        return "%s is not of the form vX.Y.Z" % new
    if last is None:
        return None if n[0] == 0 else "%s would open X=%d: a new X is the user's" % (new, n[0])
    x, y, z = parse(last)
    if n[0] != x:
        return "%s changes X after %s: a new X, v1.0.0 included, is the user's" % (new, last)
    if n in ((x, y, z + 1), (x, y + 1, 0)):
        return None
    return "%s does not follow %s: the next patch is v%d.%d.%d, the next minor v%d.%d.0" % (
        new, last, x, y, z + 1, x, y + 1)


def last_tag(repo_dir):
    tags = [t for t in git(repo_dir, "tag", "-l", "v*").split() if parse(t)]
    return max(tags, key=parse) if tags else None


def message_faults(repo_dir, rng, rules):
    """The commits in rng whose message breaks the project's commit_rules."""
    forbid = [c for c in rules.get("forbid", []) if c]
    faults = []
    for entry in git(repo_dir, "log", "--format=%h%x00%B%x01", rng).split("\x01"):
        sha, _, body = entry.strip().partition("\x00")
        if not sha:
            continue
        if rules.get("no_coauthor") and COAUTHOR.search(body):
            faults.append("%s carries a co-author trailer" % sha)
        if any(c in body for c in forbid):
            faults.append("%s holds a character the project forbids in messages" % sha)
    return faults


def why_not_written(repo_dir, tags, version):
    """Why HEAD does not say version, or None when it does."""
    if tags["version"] == "changelog":
        heads = [l for l in git(repo_dir, "show", "HEAD:CHANGELOG.md").splitlines() if l.startswith("## ")]
        if any(l.startswith("## %s (" % version) for l in heads):
            return None
        return "CHANGELOG.md at HEAD has no '## %s (date)': name the Unreleased section and commit it first" % version
    written = git(repo_dir, "show", "HEAD:VERSION").strip()
    return None if written == version[1:] else \
        "VERSION at HEAD says %s, not %s: commit the version first" % (written, version[1:])


def why_not_private(github, status):
    """Why a repository the table calls private may not be pushed as one, or None."""
    if status == 404:
        return None
    if status == 200:
        return ("%s is public on GitHub now, while the table calls it private: a public repository "
                "is pushed only after the user's ok, and the table is his to change" % github)
    return "GitHub answered %s for %s: whether it is still private is unknown" % (status, github)


def private_fault(github):
    try:
        return why_not_private(github, repos.github_status(github))
    except OSError as exc:
        return "GitHub could not be asked whether %s is still private (%s): nothing is pushed unchecked" % (github, exc)


def origin_faults(repo_dir, entry):
    """Why origin is not the repository the table names, fetch and push alike, or None."""
    for args in (("remote", "get-url", "origin"), ("remote", "get-url", "--push", "origin")):
        url = git(repo_dir, *args)
        if repos.github_of(url) != entry["github"].lower():
            return "origin (%s) is %s, not github.com:%s" % (" ".join(args[2:]), url, entry["github"])
    return None


def preflight(cwd, name, version):
    """The repository's state, checked before any build runs: (repo_dir, entry)."""
    try:
        table = repos.load(cwd)
    except ValueError as exc:
        raise Refused(str(exc))
    if name not in table:
        raise Refused("%s is not in the project's table of repositories (%s): its pushes are the "
                      "user's" % (name, ", ".join(table) or "empty"))
    entry = table[name]
    repo_dir = entry["path"]
    if version and not entry["tags"]:
        raise Refused("%s's tags are the user's: the table gives it none" % name)
    if git(repo_dir, "symbolic-ref", "--short", "HEAD") != "main":
        raise Refused("%s is not on main" % name)
    why = origin_faults(repo_dir, entry)
    if why:
        raise Refused(why)
    if entry["visibility"] == "private":
        why = private_fault(entry["github"])
        if why:
            raise Refused(why)
    git(repo_dir, "fetch", "--quiet", "--tags", "origin")
    if not is_ancestor(repo_dir, "origin/main", "HEAD"):
        raise Refused("%s's main does not go onto origin/main by fast-forward: origin moved, look "
                      "at it before anything else (never --force)" % name)
    rules = config.load_project(cwd).get("commit_rules")
    faults = message_faults(repo_dir, "origin/main..HEAD", rules if isinstance(rules, dict) else {})
    if faults:
        raise Refused("; ".join(faults))
    if version:
        check_tag(repo_dir, entry, version)
    return repo_dir, entry


def check_tag(repo_dir, entry, version):
    if git(repo_dir, "tag", "-l", version) or git(repo_dir, "ls-remote", "--tags", "origin",
                                                  "refs/tags/" + version):
        raise Refused("%s is taken: a tag is never moved" % version)
    last = last_tag(repo_dir)
    why = why_not_next(last, version)
    if why:
        raise Refused(why)
    if last and not is_ancestor(repo_dir, last, "HEAD"):
        raise Refused("HEAD does not hold %s: a tag goes on main's line" % last)
    why = why_not_written(repo_dir, entry["tags"], version)
    if why:
        raise Refused(why)


def publish(repo_dir, entry, version):
    git(repo_dir, "push", "--quiet", "origin", "main:main")
    if not version:
        return
    if entry["tags"]["annotated"]:
        git(repo_dir, "tag", "-a", version, "-m", version)
    else:
        git(repo_dir, "tag", version)
    try:
        git(repo_dir, "push", "--quiet", "origin", "refs/tags/" + version)
    except Refused:
        git(repo_dir, "tag", "-d", version, check=False)  # never published: nobody holds it
        raise


def release(cwd, name, version, build=checks.run_checks):
    """Pushes main and, with a version, tags HEAD: what was done, or Refused."""
    repo_dir, entry = preflight(cwd, name, version)
    head = git(repo_dir, "rev-parse", "--short", "HEAD")
    new = git(repo_dir, "rev-list", "--count", "origin/main..HEAD")
    if not version and new == "0":
        return "%s: nothing to push, origin/main is %s" % (name, head)
    since = (last_tag(repo_dir) if version else None) or "origin/main"
    build(name, repo_dir, entry, since, size.unattended_active(config.load_project(cwd)))
    publish(repo_dir, entry, version)
    done = "%s: pushed %s commit(s), main at %s" % (name, new, head)
    return done + (", tagged " + version if version else "")


def log(cwd, line):
    folder = config.project_dir(cwd)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "releases.log"), "a", encoding="utf-8") as fh:
        fh.write("%s %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), line))


def run_command(ident, action, name, version=None):
    """`crew.py push <repo>` and `crew.py tag <repo> vX.Y.Z`: exit 0 done, 1 refused."""
    cwd = config.locate(ident.cwd)
    if cwd is None:
        print("refused: %s has no project file; /setup makes one" % ident.cwd, file=sys.stderr)
        return 1
    what = "%s %s%s" % (name, action, " " + version if version else "")
    try:
        done = release(cwd, name, version)
    except Refused as why:
        log(cwd, "%s: refused: %s" % (what, str(why).splitlines()[0]))
        print("refused: %s" % why, file=sys.stderr)
        return 1
    log(cwd, "%s: %s" % (what, done))
    print(done)
    return 0
