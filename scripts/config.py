"""Paths, project configuration and the folder slug."""
import glob
import json
import os
import re

DEFAULTS = {"lang": "en", "warn_mb": 400, "tell_user_mb": 800}
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")


def home():
    return os.environ.get("SESSION_CREW_HOME") or os.path.expanduser("~/.session-crew")


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def raw_slug(cwd):
    """Claude Code's folder name for a cwd: every non-alphanumeric character becomes `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def slug(cwd):
    """The same, cut to 200 characters (Claude Code appends an undocumented hash past that)."""
    return raw_slug(cwd)[:200]


def transcript_dirs(cwd):
    """The `projects/` folders that may hold this cwd's transcripts."""
    projects = os.path.join(claude_dir(), "projects")
    if len(raw_slug(cwd)) <= 200:
        return [os.path.join(projects, raw_slug(cwd))]
    return sorted(glob.glob(os.path.join(glob.escape(projects), glob.escape(slug(cwd)) + "*")))


def transcript_path(cwd, session_id):
    """Where a session's transcript is, or the plain guess when it is not there."""
    for folder in transcript_dirs(cwd):
        path = os.path.join(folder, session_id + ".jsonl")
        if os.path.exists(path):
            return path
    return os.path.join(transcript_dirs(cwd)[0] if transcript_dirs(cwd) else "", session_id + ".jsonl")


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
        cfg["lang"] = "en"
    return cfg
