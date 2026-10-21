# session-crew

Hand a long-lived Claude Code session over to a fresh conversation before its transcript grows too
large. `/handoff` writes the handover, `/clear` empties the conversation, `/migrate` resumes from
the handover. A Claude Code plugin (skills and hooks); the same skills can be read by GitHub Copilot
in VS Code.

## Why

A Claude Code transcript (`~/.claude/projects/<slug>/<session>.jsonl`) only grows. A compaction
shortens the context the model sees, never the file, and VS Code can crash on a very large one (it
did, on a session of 1.4 GB). If you work by project rather than by task, one session lives for
days and gets there. session-crew warns you and the session in time, and makes the change of
conversation cheap: nothing is lost, the new conversation starts from a written handover.

The design and the facts it rests on: [docs/design.md](docs/design.md).

## Install

```
/plugin marketplace add debug922/session-crew
/plugin install session-crew@session-crew
```

From a local clone: `/plugin marketplace add ./session-crew`, then the same `/plugin install`.
If another size hook is already in your `settings.json` under `UserPromptSubmit`, remove it: both
would run.

## Use

**Same tab.** Past `warn_mb` the size hook tells the session to close the item under way and run
`/handoff`, which writes the handover under `~/.session-crew/<slug>/<name>/` (the slug is the
folder path with every non-alphanumeric character turned into `-`). While it is pending you are
reminded on every message. Type `/clear`; the SessionStart hook announces the handover; type
`/migrate`: it reads the handover, says who the session is and what comes next, and marks it used.
You can run `/handoff` whenever you like, not only when warned.

**New tab.** In a new tab of the same folder, type `/migrate <name>`. The rename hook gives the new
session the old one's name (see below), then `/migrate` goes on as above.

**After a crash.** With no handover, `/migrate` recovers from the old transcript: the last
compaction summary and the text of the messages after it.

The handover has four sections: `## Work under way`, `## Last requests and decisions` (your own
words, quoted), `## What remains`, `## Where things are`. `handoff save` refuses a body missing one.

## Configuration

Optional, in `~/.session-crew/<slug>/project.json`; a missing or partial file gives the defaults.

| Field | Default | Meaning |
|---|---|---|
| `lang` | `"en"` | language of the messages to you (`en`, `it`); context for the session is English |
| `warn_mb` | `400` | transcript size at which the session is told to hand over |
| `tell_user_mb` | `800` | size at which you are told too |
| `unattended` | none | the unattended-night block below; without it there is no night logic |
| `sessions` | none | `{"name", "role", "owns"}` entries `/migrate` prints for the session |

The `unattended` block is for a long run you leave alone (a night):

- `status_command`: argument list (no shell, 3 s timeout) that reports whether the night is on, for
  example `["my-mode-tool", "status"]`; a failure counts as "not on".
- `active_pattern`: regex matched against its output, per line, for example `^mode: night`.
- `ceiling_mb` (default `1000`): while a night is on, the size is ignored below this; above it the
  session parks its queue and hands over, and you are not bothered.
- `start_prefixes`: texts a prompt starts with (case and spaces ignored) when you start a night. If
  the session is already past `warn_mb` you are told to hand over first.
- `modes` (default `["auto", "dontAsk", "bypassPermissions"]`): the permission modes fit for a
  night. If the prompt starts a night in another mode (`default`, `plan`, `acceptEdits`), you and
  the session are warned that a permission request would stop the run until the morning.

## The rename hook

It acts only when your prompt is exactly `/migrate <name>`, a pending handover exists for that name
in this folder, and this session is not already called that. Then:

- If an older session holds the name in the same folder and is idle, it sends it SIGTERM, but only
  after checking the process start time recorded in its registry file against the live process (a
  reused pid is never signalled). Once the process is gone the new session takes the name.
- It never signals a session that is busy, waiting, unverifiable, or that does not stop: it tells
  the session why and leaves the name where it is.

A name can be trusted by other tools, so this hook is deliberately narrow. Read
[docs/design.md](docs/design.md#6-the-rename-hook-fallback-path-only) before you rely on it.

## Copilot

The skills (`skills/*/SKILL.md`) read in Copilot. The script has no session registry there, so you
pass `--name` and `--cwd` and an explicit path: `python3 -I /path/to/scripts/crew.py handoff save
--name NAME --cwd DIR`. There are no size or rename hooks for Copilot yet.

## Requirements

Python 3 (standard library only) and `ps`. Tested on macOS; Linux is expected to work and is run in
CI. Windows is not supported.

## Tests

```
python3 -I -m unittest discover -s tests
```

Every case runs in a temporary folder through `SESSION_CREW_HOME` and `CLAUDE_CONFIG_DIR`, never
your real `~/.session-crew` or `~/.claude`.

## Limits

- Claude Code details used here (`/clear` keeping the name, `sessionTitle`, the registry in
  `~/.claude/sessions`) are observed, partly undocumented, and may change.
- A `UserPromptSubmit` hook cannot tell typing from a message sent by a `/loop` or another session.
- The rename hook cannot rename a session that is running elsewhere; only you can, from its tab.
- The size is the file size; the hook never blocks a message.

## License

MIT, see [LICENSE](LICENSE).
