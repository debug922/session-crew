"""Where a `git push` goes, read from the repository's configuration now: every place it pushes to
must resolve to a URL, or the guard cannot say it is not a table repository's."""
import re
import subprocess

URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|[\w.-]+@[\w.-]+:|/|\./|\.\./|~)", re.IGNORECASE)
VALUE_FLAGS = {"-o", "--push-option", "--receive-pack", "--exec"}


def config(top, *args):
    """`git config` lines of the repository at top; None when the key is unset."""
    out = subprocess.run(["git", "-C", top, "config", *args], capture_output=True, text=True,
                         timeout=5)
    return out.stdout.split("\n")[:-1] if out.returncode == 0 else None


def target(args):
    """The remote or URL a push names: --repo, else the first word that is not a flag."""
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a in VALUE_FLAGS:
            i += 2
            continue
        if a == "--repo" and i + 1 < len(args):
            return args[i + 1]
        if a.startswith("--repo="):
            return a.split("=", 1)[1]
        if not a.startswith("-"):
            pos.append(a)
        i += 1
    return pos[0] if pos else None


def default_remote(top):
    branch = subprocess.run(["git", "-C", top, "symbolic-ref", "--short", "-q", "HEAD"],
                            capture_output=True, text=True, timeout=5).stdout.strip()
    for key in (["branch.%s.pushRemote" % branch] if branch else []) + ["remote.pushDefault"] + (
            ["branch.%s.remote" % branch] if branch else []):
        found = config(top, "--get", key)
        if found:
            return found[-1]
    return "origin"


def rewritten(top, url):
    """url as git would push it: the longest matching url.<base>.pushInsteadOf, else insteadOf."""
    rules = {"pushinsteadof": [], "insteadof": []}
    for line in config(top, "--get-regexp", r"^url\..*insteadof$") or []:
        key, _, prefix = line.partition(" ")
        kind = key.rsplit(".", 1)[1]
        if kind in rules and key.startswith("url."):
            rules[kind].append((prefix, key[4:key.rindex(".")]))
    for kind in ("pushinsteadof", "insteadof"):
        hits = [(p, b) for p, b in rules[kind] if p and url.startswith(p)]
        if hits:
            prefix, base = max(hits, key=lambda h: len(h[0]))
            return base + url[len(prefix):]
    return url


def destinations(top, args):
    """The URLs a push in the repository at top goes to (url.*.insteadOf applied), or None when
    they cannot be told (a remote that is not in the configuration now)."""
    where = target(args) or default_remote(top)
    if URL.match(where):
        urls = [where]
    else:
        urls = config(top, "--get-all", "remote.%s.pushurl" % where) \
            or config(top, "--get-all", "remote.%s.url" % where)
    return [rewritten(top, u) for u in urls] if urls else None


def alias_value(start, name):
    """What `git config --get alias.NAME` says from start, or None."""
    try:
        found = config(start, "--get", "alias." + name)
    except (OSError, subprocess.SubprocessError):
        return None
    return found[-1] if found else None
