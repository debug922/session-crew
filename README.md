# session-crew

Hand a long-lived Claude Code session over to a fresh conversation before its transcript grows too
large. `/handoff` writes the handover, `/clear` empties the conversation, `/migrate` resumes from
the handover. A Claude Code plugin (skills and hooks); the same skills can be read by GitHub Copilot
in VS Code. Since 0.2 it also carries a project's git flow, configured in chat with `/setup`.

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

## Commands

| Command | What it does | When |
|---|---|---|
| `/handoff` | writes this session's handover: the work under way, your last requests and decisions in your words, what remains, where things are | when the size hook tells you, or whenever you like |
| `/migrate` | reads the pending handover, says who the session is and what comes next, and marks the handover used; with no handover, recovers from the old transcript | after `/clear`, in the same tab |
| `/migrate <name>` | the same, and gives this session the old one's name first (see [the rename hook](#the-rename-hook)) | in a new tab of the same folder |
| `/setup` | makes or changes the project's configuration in chat, with options to choose from, and writes it only on your yes | once per project, and when the workflow changes |
| `/push <repo>` | pushes a linked repository's main through the door, after its checks (see [the git flow](#the-git-flow)) | when what is committed is ready |
| `/release <repo> vX.Y.Z` | the same, and tags the release | when the version is written and committed |

Each is also reachable by its full name (`/session-crew:handoff`, `/session-crew:setup`, ...) when
another plugin uses the same word. Under Copilot the same skills are read from `skills/*/SKILL.md`
and the script takes `--name` and `--cwd` (see [Copilot](#copilot)).

Without a command, five hooks act on their own: the size hook on every message (past `warn_mb`
it tells the session to hand over), the start hook after `/clear` or at startup (it announces a
pending handover), the rename hook (only on a prompt that is exactly `/migrate <name>`), and the two
guards of [the git flow](#the-git-flow), which say nothing in a folder with no project file.

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
| `commit_rules` | none | what the door refuses in the messages of the commits it pushes: `{"no_coauthor": true, "forbid": [characters]}`, the characters written as JSON escapes |
| `repos` | none | the table of linked repositories the door and the guards read (below) |

`/setup` writes this file for you; `crew.py config show` prints it and what it lacks.

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

## The git flow

For a project that links git repositories (`repos` in its file) the plugin gives its sessions one
door: `/push <repo>` and `/release <repo> vX.Y.Z` run `crew.py push` and `crew.py tag`. Each entry
of `repos` is `{"name", "path", "github", "visibility", "pushers", "checks", "tags"}`:

- `github` is `owner/name`; only GitHub's repositories can be linked, since the door asks GitHub
  (without credentials) whether a repository the table calls `private` still is. `visibility` is
  `private` or `public`; a public push asks you first.
- `pushers` are the session names (the ones you gave) that may push it; an agent never does.
- `checks` run in a clean worktree of HEAD before a push: a preset (`go`: vet, test, govulncheck;
  `unittest`; `frontend`: typecheck and tests when `frontend/` changed) or an object
  `{"run": [argv], "in": "dir", "when_changed": "dir", "in_repo": false}`.
- `tags` is `null` (the tags are yours) or `{"version": "changelog" or "file", "annotated": bool}`:
  where the version is written, and the tag's style. Only the next patch or minor of the last tag
  with the same X is accepted, on main's line, never moved.

Before anything leaves, the door checks that main is checked out, origin is the table's repository,
main goes onto origin/main by fast-forward, the commits meet `commit_rules`, and the checks pass.
Each run is in `~/.session-crew/<slug>/releases.log`.

The door does not trust the guard. It finds its caller by the process ancestry (never by a flag: it
takes no `--name` or `--session-id`), refuses when no Claude Code session is above it, refuses a
session that is not among the repository's pushers, finds the project from the process's own
folder, and refuses a public repository while a night is on. Only two things are the guard's alone:
that an agent never opens the door, and the ask before a public push by day.

All of these checks rest on Claude Code's registry of sessions (`~/.claude/sessions`), which only
Claude Code writes. The door reads it through the process ancestry and trusts a file only when its
`procStart` matches the live process, so a stale file under a reused pid never counts; the guard
refuses (a deny, never an ask) any write into that folder, or a move of it or of the config folder,
from a Bash line or a file tool, in every folder, configured or not.

The guard (PreToolUse, for Bash and for the file tools) holds the rest, for the project of the
event's folder:

- a line that has a word under the installed plugin's folder (or a glob that could match one
  there), or that runs a script named `crew.py` (the program word, or python's script argument, also
  inside `bash -c`, heredocs fed to a shell, `$(...)` and backticks), must be exactly one of the
  allowed shapes (the door lines, `config show|discover|apply`, and v1's own `handoff`, `migrate`,
  `recover`, `size` and `hook` forms), alone on its line by the plugin's own path, with no env prefix, `bash -c`, `$(...)` or extra
  words; anything else is refused and the refusal lists the shapes. A `crew.py` that is only an argument of git, grep or an editor is not run, so
  working on a copy of this repository is not held up; a plain read (`cat`, `grep`, `ls`) of the plugin is free. A `crew.py` that is not the installed one may run v1's own shapes and `config show|discover`, never `push`, `tag` or `config apply`; if you load the plugin from a working checkout (`--plugin-dir`), commands naming that checkout are held to the shapes, since it is the plugin's folder for the guard. The door's line also needs a session the table names as a pusher,
  never an agent; a public repository asks you;
- in a project with a table, `git push` passes only when the guard places the repository (no `cd`,
  env prefix, `--git-dir` or `--work-tree`), it is not in the table, and every place the push goes
  resolves to a URL (read from the repository's configuration now, `insteadOf` applied) that is not
  a table repository's; anything it cannot resolve, a remote added in the same line included, is
  refused. `git tag` that creates or deletes a tag in a table repository is refused. Git is also
  looked for inside `bash -lc '...'`, heredocs that feed a shell, `$(...)`, backticks and aliases
  (and defining an alias that hides a push or a tag is refused);
- a push that deletes or rewrites on the remote (`--force`, `--delete`, a refspec with `+` or `:`,
  `--mirror`, `--prune`), a `gh` command that deletes, a DELETE to GitHub's API: asks you;
- `config apply`, any write (a verb, a redirection, inline interpreter code, or a file tool) to
  anything under `~/.session-crew`, to a `project.json` there (by its path as written or its real
  one), and any write into the plugin's folder: asks you. Reading is free;
- while a night is on (`unattended.status_command`) every ask is a refusal, since nobody is there.

**A folder with no `project.json` gets no git rules and no shape rules**: `/push` has no table and
the guard says nothing about pushes, tags or the scripts. The configuration itself is guarded
everywhere: `config apply` and writes to the crew home or the plugin's folder ask you, since that
file is what grants pushes. What you want everywhere (your punctuation, your secrets) stays in your
own hooks; a plugin's guard can add asks and refusals but never loosen yours (deny wins).

**What the guard is.** It stops mistakes and the common forms of them. A session set on getting
round it can, with a script of its own (a heredoc fed to an interpreter, a program it wrote). What
is left is the door's own checks, which do not depend on the guard, and your rule against working
around a guard. A running tab sees the guard only after `/reload-plugins`.

Under Copilot there is no guard and no door: `/setup` works there, and `config apply` outside Claude
Code (decided by the process ancestry alone) prints the line for you to run in your own terminal. It
writes only when stdin is a terminal and you type `yes`, and refuses otherwise.

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
