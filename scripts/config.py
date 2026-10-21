"""Paths, project configuration and the folder slug."""
import json
import os
import re

DEFAULTS = {"lang": "it", "warn_mb": 400, "tell_user_mb": 800}
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def home():
    return os.environ.get("SESSION_CREW_HOME") or os.path.expanduser("~/.session-crew")


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def slug(cwd):
    return cwd.replace("/", "-")


def project_dir(cwd):
    return os.path.join(home(), slug(cwd))


def safe_name(name):
    """A name fit to be a folder name: anything outside the allowed set becomes `_`."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:64].lstrip(".-_") or "_"
    return cleaned


def load_project(cwd):
    """project.json merged over the defaults; a missing or broken file gives the defaults."""
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(project_dir(cwd), "project.json"), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    if cfg.get("lang") not in ("it", "en"):
        cfg["lang"] = "it"
    return cfg
