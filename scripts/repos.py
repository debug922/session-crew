"""The table of the linked repositories: `repos` of a project's project.json (section 11.2).

One entry a repository: name, path (~ allowed), github (owner/name), visibility (private or
public), pushers (session names), checks (presets or objects), tags (null or {version, annotated}).
A table that cannot be read, or an entry not of this shape, refuses every door command.
"""
import http.client
import json
import os
import re
import urllib.error
import urllib.request

import config

PRESETS = ("go", "unittest", "frontend")
VISIBILITY = ("private", "public")
NAME = re.compile(r"[A-Za-z0-9][\w.-]{0,63}")
GITHUB = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*")
GITHUB_URL = re.compile(r"(?:git@github\.com:|(?:https|ssh)://(?:[^@/]+@)?github\.com/)"
                        r"([\w.-]+/[\w.-]+?)(?:\.git)?/?", re.IGNORECASE)
CHECK_KEYS = {"run", "in", "when_changed", "in_repo"}


def github_of(url):
    """owner/name of a GitHub remote's URL, lowered; None for a URL that is not GitHub's."""
    m = GITHUB_URL.fullmatch((url or "").strip())
    return m.group(1).lower() if m else None


def _relative_dir(value):
    return isinstance(value, str) and value != "" and not os.path.isabs(value) \
        and ".." not in value.split("/")


def why_not_check(name, item):
    """Why a check is neither a preset's name nor an object of the shape, or None."""
    if isinstance(item, str):
        return None if item in PRESETS else \
            "%s: check %r is not a preset (%s)" % (name, item, ", ".join(PRESETS))
    if not isinstance(item, dict):
        return "%s: a check is a preset's name or an object" % name
    extra = set(item) - CHECK_KEYS
    run = item.get("run")
    if extra:
        return "%s: a check has no field %s" % (name, ", ".join(sorted(extra)))
    if not isinstance(run, list) or not run or not all(isinstance(a, str) and a for a in run):
        return "%s: a check's run is a non-empty list of arguments" % name
    for key in ("in", "when_changed"):
        if key in item and not _relative_dir(item[key]):
            return "%s: a check's %s is a folder inside the repository" % (name, key)
    if "in_repo" in item and not isinstance(item["in_repo"], bool):
        return "%s: a check's in_repo is true or false" % name
    return None


def why_not_entry(e):
    """Why an entry is not of the table's shape, or None when it is."""
    if not isinstance(e, dict):
        return "an entry is not an object"
    name = e.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return "name %r is not a repository's name" % (name,)
    path = e.get("path")
    if not isinstance(path, str) or not path:
        return "%s: path missing" % name
    if not os.path.isabs(os.path.expanduser(path)):
        return "%s: path is neither absolute nor under ~" % name
    if not isinstance(e.get("github"), str) or not GITHUB.fullmatch(e["github"]):
        return "%s: github is not owner/name (only GitHub's repositories can be linked)" % name
    if e.get("visibility") not in VISIBILITY:
        return "%s: visibility is neither private nor public" % name
    pushers = e.get("pushers", [])
    if not isinstance(pushers, list) or not all(isinstance(p, str) and NAME.fullmatch(p) for p in pushers):
        return "%s: pushers is not a list of session names" % name
    checks = e.get("checks", [])
    if not isinstance(checks, list):
        return "%s: checks is not a list" % name
    for item in checks:
        why = why_not_check(name, item)
        if why:
            return why
    tags = e.get("tags")
    if tags is not None and not (isinstance(tags, dict) and set(tags) == {"version", "annotated"}
                                 and tags["version"] in ("changelog", "file")
                                 and isinstance(tags["annotated"], bool)):
        return "%s: tags is neither null nor {version: changelog or file, annotated: true or false}" % name
    return None


def problems(entries):
    """Every reason a list of entries is not a table, in order; empty when it is one."""
    if not isinstance(entries, list):
        return ["repos is not a list"]
    out, seen = [], set()
    for e in entries:
        why = why_not_entry(e)
        if why:
            out.append(why)
        elif e["name"] in seen:
            out.append("%s is listed twice" % e["name"])
        else:
            seen.add(e["name"])
    return out


class Table:
    """What a folder's project.json says about the git flow.

    exists: there is a project file; active: the flow acts (a `repos` key that is not an empty
    list, or a file that cannot be read); entries: the table by name, None when it cannot be
    read; error: why not."""

    def __init__(self, exists=False, active=False, entries=None, error=None):
        self.exists, self.active, self.entries, self.error = exists, active, entries, error


def read(cwd):
    path = config.project_file(cwd)
    if not os.path.isfile(path):
        return Table()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return Table(True, True, None, "the table of repositories cannot be read (%s): %s" % (path, exc))
    if not isinstance(data, dict) or "repos" not in data:
        return Table(True, False, None, "%s has no list \"repos\"" % path)
    wrong = problems(data["repos"])
    if wrong:
        return Table(True, True, None, "%s: %s" % (path, wrong[0]))
    table = {e["name"]: dict(e, path=os.path.expanduser(e["path"]), pushers=e.get("pushers", []),
                             checks=e.get("checks", []), tags=e.get("tags")) for e in data["repos"]}
    return Table(True, bool(table), table, None)


def load(cwd):
    """The table by name; ValueError when it cannot be read or an entry is not of its shape."""
    t = read(cwd)
    if t.entries is None:
        raise ValueError(t.error or "no project file")
    return t.entries


def expand_checks(items, night):
    """The checks as objects the door runs: presets opened, the limits of the mode applied."""
    out = []
    for item in items:
        if item == "go":
            env = {"GOWORK": "off"}
            out += [{"run": ["go", "vet", "./..."], "env": env},
                    {"run": ["go", "test", "-count=1", "-p", "8" if night else "2", "./..."],
                     "env": env},
                    {"run": ["govulncheck", "./..."], "env": env}]
        elif item == "unittest":
            out.append({"run": ["python3", "-I", "-m", "unittest", "discover", "-s", "tests"]})
        elif item == "frontend":
            base = {"in": "frontend", "when_changed": "frontend", "in_repo": True,
                    "env": {"CI": "true"}}
            out += [dict(base, run=["npm", "run", "typecheck"]), dict(base, run=["npm", "test"])]
        else:
            out.append(item)
    return out


def github_status(github):
    """The HTTP status GitHub's API answers a request with no credentials for owner/name: 404 for a
    private repository (or none at all), 200 for a public one. OSError when it cannot be asked."""
    req = urllib.request.Request("https://api.github.com/repos/" + github,
                                 headers={"User-Agent": "session-crew", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, http.client.HTTPException) as exc:
        raise OSError(str(exc))


def visibility_of(github):
    """private, public, or unknown (GitHub could not be asked, or answered something else)."""
    try:
        status = github_status(github)
    except Exception:  # noqa: BLE001 - http.client errors, TLS, anything: unknown, never a crash
        return "unknown"
    return {404: "private", 200: "public"}.get(status, "unknown")
