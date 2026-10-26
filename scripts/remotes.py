"""Reading a git remote's URL: which GitHub repository it names, however it is spelled.

parse(url) gives ("github", "owner/name") for any spelling of a GitHub repository (scp-like or
ssh://, https://, git://, a port, ssh.github.com, www.github.com, a trailing slash, a query or a
fragment, any case), ("other", None) for a local path or another host, and ("bad", None) for a
URL that names GitHub but does not parse to one repository, or cannot be read at all. A caller
that guards a table of repositories refuses "bad": it fails closed.
"""
import re
from urllib.parse import urlsplit

GITHUB_HOSTS = {"github.com", "www.github.com", "ssh.github.com"}
SCP = re.compile(r"([^:/\s]+@)?([^:/\s@]+):(?!//)(.*)", re.DOTALL)
NAME = re.compile(r"[\w.-]+")


def _repository(path):
    """owner/name (lowered) from a URL path, or None when it is not exactly two names."""
    path = re.split(r"[?#]", path, maxsplit=1)[0].strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) == 2 and all(NAME.fullmatch(p) for p in parts):
        return "/".join(parts).lower()
    return None


def parse(url):
    text = (url or "").strip()
    if not text:
        return "bad", None
    if "://" in text:
        try:
            split = urlsplit(text)
            host, path = (split.hostname or "").lower(), split.path
        except ValueError:
            return ("bad", None) if "github" in text.lower() else ("other", None)
        if split.scheme.lower() == "file":
            return "other", None
    else:
        m = None if text.startswith(("/", ".", "~")) else SCP.fullmatch(text)
        if not m:
            return "other", None  # a local path
        host, path = m.group(2).lower(), m.group(3)
    if host not in GITHUB_HOSTS:
        return ("bad", None) if "github.com" in host else ("other", None)
    name = _repository(path)
    return ("github", name) if name else ("bad", None)
