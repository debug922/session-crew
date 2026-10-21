# session-crew

Hand a long-lived coding session over to a fresh conversation before its transcript grows too
large: `/handoff` writes the handover, `/migrate` resumes it. A Claude Code plugin (skills and
hooks); the same skills serve GitHub Copilot in VS Code.

The design and the facts it rests on: [docs/design.md](docs/design.md).

## The two flows

**Same tab.** Past `warn_mb` the size hook tells the session to close the item under way and run
`/handoff`, which writes the handover under `~/.session-crew/<slug>/<name>/`. While it is pending the
maintainer is reminded on every message; he types `/clear`, the SessionStart hook announces the
handover, and `/migrate` reads it, says who the session is and marks it used.

**New tab.** In a new tab of the same folder he types `/migrate <name>`: the rename hook frees the
name (SIGTERM to an idle holder, nothing to a busy one) and gives it to the new session. After a
crash with no handover, `/migrate` recovers from the old transcript.

## Tests

```
python3 -I -m unittest discover -s tests
```

Stdlib only; every case runs in a temporary folder through `SESSION_CREW_HOME` and
`CLAUDE_CONFIG_DIR`, never the real `~/.session-crew` or `~/.claude`.

## Install

The maintainer's steps are in section 11 of [docs/design.md](docs/design.md#11-install-the-maintainers).
