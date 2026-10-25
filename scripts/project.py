"""project.json beyond v1's defaults: validation of a whole file, the diff of a draft, the write."""
import json
import os
import re
import shutil

import config
import repos

KNOWN = {"lang", "warn_mb", "tell_user_mb", "unattended", "sessions", "commit_rules", "repos"}
MODES = {"default", "plan", "acceptEdits", "auto", "dontAsk", "bypassPermissions"}


def _number(v):
    return type(v) in (int, float) and v > 0


def _strings(v):
    return isinstance(v, list) and all(isinstance(x, str) and x for x in v)


def _unattended(un):
    if not isinstance(un, dict):
        return ["unattended is not an object"]
    out = []
    if "status_command" in un and not (_strings(un["status_command"]) and un["status_command"]):
        out.append("unattended.status_command is a non-empty list of arguments")
    if "active_pattern" in un:
        try:
            re.compile(un["active_pattern"])
        except (re.error, TypeError):
            out.append("unattended.active_pattern is not a regular expression")
    if "start_prefixes" in un and not _strings(un["start_prefixes"]):
        out.append("unattended.start_prefixes is a list of texts")
    if "ceiling_mb" in un and not _number(un["ceiling_mb"]):
        out.append("unattended.ceiling_mb is a positive number")
    if "modes" in un and not (_strings(un["modes"]) and set(un["modes"]) <= MODES):
        out.append("unattended.modes holds only %s" % ", ".join(sorted(MODES)))
    return out


def _sessions(sessions):
    if not isinstance(sessions, list):
        return ["sessions is not a list"]
    out = []
    for s in sessions:
        if not (isinstance(s, dict) and isinstance(s.get("name"), str)
                and config.NAME_RE.fullmatch(s["name"])):
            out.append("a session entry needs a name")
        elif not isinstance(s.get("role", ""), str) or not _strings(s.get("owns", [])):
            out.append("session %s: role is a text and owns a list of texts" % s["name"])
    return out


def _commit_rules(rules):
    if not isinstance(rules, dict) or set(rules) - {"no_coauthor", "forbid"}:
        return ["commit_rules holds only no_coauthor and forbid"]
    out = []
    if "no_coauthor" in rules and not isinstance(rules["no_coauthor"], bool):
        out.append("commit_rules.no_coauthor is true or false")
    if "forbid" in rules and not _strings(rules["forbid"]):
        out.append("commit_rules.forbid is a list of characters")
    return out


def validate(data):
    """(errors, warnings) of a whole project file; an empty first list means it can be written."""
    if not isinstance(data, dict):
        return ["the project file is not an object"], []
    errors = []
    if "lang" in data and data["lang"] not in ("it", "en"):
        errors.append("lang is it or en")
    for key in ("warn_mb", "tell_user_mb"):
        if key in data and not _number(data[key]):
            errors.append("%s is a positive number" % key)
    if _number(data.get("warn_mb")) and _number(data.get("tell_user_mb")) \
            and data["warn_mb"] > data["tell_user_mb"]:
        errors.append("warn_mb is over tell_user_mb")
    for key, check in (("unattended", _unattended), ("sessions", _sessions),
                       ("commit_rules", _commit_rules), ("repos", repos.problems)):
        if key in data:
            errors += check(data[key])
    unknown = sorted(set(data) - KNOWN)
    return errors, ["field %s is not one session-crew reads" % k for k in unknown]


def _show(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=True)


def _by_name(items):
    if isinstance(items, list) and all(isinstance(i, dict) and "name" in i for i in items):
        return {i["name"]: i for i in items}
    return None


def diff(old, new):
    """What changes from old to new, field by field and, for repos and sessions, name by name."""
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        named_a = _by_name(a if key in old else [])
        named_b = _by_name(b if key in new else [])
        if named_a is not None and named_b is not None:
            out += _diff_named(key, named_a, named_b)
        elif key not in old:
            out.append("%s: added %s" % (key, _show(b)))
        elif key not in new:
            out.append("%s: removed" % key)
        else:
            out.append("%s: %s -> %s" % (key, _show(a), _show(b)))
    return out


def _diff_named(key, a, b):
    out = []
    for name in sorted(set(a) | set(b)):
        if name not in a:
            out.append("%s %s: added %s" % (key, name, _show(b[name])))
        elif name not in b:
            out.append("%s %s: removed" % (key, name))
        elif a[name] != b[name]:
            for f in sorted(set(a[name]) | set(b[name])):
                if a[name].get(f) != b[name].get(f):
                    out.append("%s %s: %s %s -> %s" % (key, name, f, _show(a[name].get(f)),
                                                      _show(b[name].get(f))))
    return out


def read_current(cwd):
    """The project file as written ({} when there is none or it is not an object)."""
    try:
        with open(config.project_file(cwd), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def drafts_dir(cwd):
    return os.path.join(config.project_dir(cwd), "drafts")


def read_draft(cwd, path):
    """A draft's JSON; ValueError when it is not inside this project's drafts folder."""
    full = os.path.realpath(os.path.join(drafts_dir(cwd), path) if not os.path.isabs(path) else path)
    if os.path.dirname(full) != os.path.realpath(drafts_dir(cwd)):
        raise ValueError("a draft lives in %s" % drafts_dir(cwd))
    try:
        with open(full, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise ValueError("the draft cannot be read: %s" % exc)


def write(cwd, data):
    """Keep the previous file as project.json.prev, then write the new one through a rename."""
    path = config.project_file(cwd)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        shutil.copyfile(path, path + ".prev")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")
    os.replace(tmp, path)
