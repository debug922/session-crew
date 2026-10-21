# session-crew v1: design

Approved by the maintainer on 2026-10-21 (the design, then S1 to S3 the same evening). This file is
the brief's source: what v1 does, the facts it rests on, and the contracts each part keeps.

## 1. Purpose

A Claude Code transcript only grows: a compaction shortens the context, never the file. On
2026-10-21 a session of 1.4 GB on disk took VS Code down with it. The maintainer works by project,
not by task, so one session lives for days. session-crew:
- tells the session, and then the maintainer, when to hand over;
- writes the handover (`/handoff`) and resumes it in a fresh conversation (`/migrate`);
- keeps an unattended night going: the size never stops a night started in a light session.

The same `SKILL.md` files serve GitHub Copilot in VS Code (section 9).

## 2. Facts it rests on (checked 2026-10-21, Claude Code 2.1.301 to 2.1.306)

1. **`/clear` keeps the name.** With no argument it starts a new conversation in the same process:
   same pid, same name and `nameSource`, a new session id and a new `.jsonl`. Measured on one live
   session: session d0c12f77 (551 MB) became 0cbe5002 (2 KB), name kept. VS Code's memory did not drop, and
   had not held the 551 MB to begin with.
2. **Session registry**: `~/.claude/sessions/<pid>.json` holds `pid`, `sessionId`, `cwd`, `name`,
   `nameSource`, `status` (`idle`, `busy`, `waiting`), `updatedAt`. A file can outlive its process:
   check the pid is alive.
3. **Transcripts**: `~/.claude/projects/<slug>/<sessionId>.jsonl`, where the slug is the cwd with
   every non-alphanumeric character (`/`, dots, underscores, spaces, ...) turned into `-`
   (`/home/x/code/app` is `-home-x-code-app`). A slug over 200 characters is cut to 200 and a hash of
   the full path is appended (the hash is undocumented): the code that looks for transcripts globs
   `<first 200 characters>*` under `projects/`. `~/.session-crew/<slug>/` uses the same slug cut to
   200, with no hash. Records used here:
   - `{"type": "custom-title", "customTitle": "<name>", "sessionId": ...}`, repeated through the file;
   - a compaction is a `system` record with `"subtype": "compact_boundary"`, followed by a `user`
     record with `"isCompactSummary": true` whose `message.content` is the summary;
   - `user` and `assistant` records carry `message.content`, a string or a list of parts (`text`,
     `tool_use`, `tool_result`, ...).
4. **UserPromptSubmit fires on more than typing**: messages from other sessions, each `/loop`
   iteration, a background agent reporting back. No field of its input marks what the human typed.
   A typed slash command reaches the hook as typed (`/migrate kcalloc` in `prompt`). A message from
   another session never executes a command; a `/loop` prompt can.
5. **`hookSpecificOutput.sessionTitle`**, on UserPromptSubmit and on SessionStart (sources
   `startup`, `resume`, `fork`), sets the name as `/rename` does; Claude Code records it with
   `nameSource: "user"`, which other tools may take as proof of a name (kcalloc, the project this was first written
   for, has a release door that does), hence the care of the rename hook. Undocumented, and from the
   binary apparently not applied: a name another live session holds.
6. **No way to rename another running session**: only the maintainer can, from its own tab.
7. **Plugins**: `.claude-plugin/plugin.json` (only `name` required), `skills/<name>/SKILL.md`,
   `hooks/hooks.json` (event map under a top-level `"hooks"` key, commands quoted with
   `"${CLAUDE_PLUGIN_ROOT}/..."`). A plugin's hooks add to those of `settings.json` and never
   replace them. Local install: a `.claude-plugin/marketplace.json` in the repo, then
   `/plugin marketplace add <dir>` and `/plugin install <plugin>@<marketplace>`; a relative-path
   plugin loads in place.
8. **`python3 -I` drops the script's folder from `sys.path`** (it implies `-P`): an entry script
   inserts its own folder before importing its siblings.

## 3. The flow

**Primary: the same tab.**
1. Past `warn_mb` the size hook tells the session (section 5); the session closes the item under
   way and runs `/handoff` at the next pause. The maintainer may run `/handoff` whenever he likes.
2. While a pending handoff exists for this session's name and folder, the size hook tells the
   maintainer on every message: *"Passaggio pronto: scrivi /clear e poi /migrate."* (with `lang` `it`)
3. He types `/clear`. The SessionStart hook (source `clear`, and `startup`) sees the pending
   handoff for its name and tells both: *"/migrate"*.
4. `/migrate` reads the handoff, summarises it in a few lines, says who the session is (section 8)
   and marks the handoff used.

**Fallback: a new tab.** He opens a new tab in the same folder and types `/migrate <name>`.
The rename hook (section 6) frees the name and gives it to the new session; `/migrate` then goes
on as in step 4.

**After a crash**, with no handoff: `/migrate` recovers from the old transcript (section 7).

## 4. Files and configuration

Everything lives under `~/.session-crew/<slug>/`, outside every repository, the slug as in 2.3:
- `project.json`, optional; defaults when missing or partial:
  ```json
  {
    "lang": "en",
    "warn_mb": 400,
    "tell_user_mb": 800,
    "unattended": {
      "status_command": ["my-mode-tool", "status"],
      "active_pattern": "^mode: night",
      "start_prefixes": ["start the night"],
      "ceiling_mb": 1000,
      "modes": ["auto", "dontAsk", "bypassPermissions"]
    },
    "sessions": [
      {"name": "backend", "role": "the backend: api, workers, CI",
       "owns": ["api", "workers"]}
    ]
  }
  ```
  The `unattended` block is an example, not a default (`modes` alone has one, shown). The first
  project that used session-crew reads its own mode tool; any command that prints a line the
  pattern matches will do. Without `unattended` there is no unattended mode. The status command runs without a shell, with a
  3 s timeout; a failure counts as attended.
- `<name>/<UTC yyyymmddThhmmssZ>-<session id, 8 chars>.md`: one handover. Front matter
  `status` (`pending` or `used`), `name`, `cwd`, `session_id`, `written_at`, and once used
  `used_at`, `used_by`. Sections, in order: `## Work under way`, `## Last requests and
  decisions` (the user's own words, quoted), `## What remains`, `## Where things are` (branches, unpushed
  commits, run folders). Never a copy of the memory: it points to it.
- An unnamed session uses `unnamed-<session id, 8 chars>`.

**Who the script is.** In Claude Code, the script walks up its parent pids to the first with a
registry file: that file gives its session id, name and cwd. `--name`, `--session-id` and `--cwd`
override (Copilot passes them; there is no registry there).

## 5. The size hook (replaces kcalloc's first `kc_size.py`)

UserPromptSubmit, reads `transcript_path`'s size. Never holds up a message: on any error it writes
to stderr and exits 1. Output: `hookSpecificOutput.additionalContext` for the session,
`systemMessage` for the maintainer, both optional.

Attended (no unattended config, or the status command does not match):

| Size | To the session | To the maintainer |
|---|---|---|
| below `warn_mb` | nothing | the pending-handoff line of 3.2, if any |
| `warn_mb` and over | close the item, `/handoff` at the next pause, no new item | the same line, if any |
| `tell_user_mb` and over | the same | *"Questa sessione pesa N MB: /handoff, /clear, /migrate."* |

**Starting a night (S2).** When the prompt, stripped and lowercased, starts with one of
`start_prefixes` and the size is `warn_mb` or over: to the maintainer *"Questa sessione pesa N MB:
prima della notte /handoff, /clear, /migrate, poi ripeti il comando."*; to the session: do not start
the unattended run in this conversation, say why. Matching text is safe here: it only warns.

Unattended (the status command matches `active_pattern`) (S3):
- below `ceiling_mb`: nothing, whatever `warn_mb` says;
- `ceiling_mb` and over: to the session, park the queue at the next release point, write the
  handoff and the report; nothing to the maintainer (he is away).

**The permission mode of a night (N3).** When the prompt starts a night (the same test as S2), the
hook also reads the event's `permission_mode` (`default`, `plan`, `acceptEdits`, `auto`, `dontAsk`,
`bypassPermissions`). If it is not in `unattended.modes` (default `["auto", "dontAsk",
"bypassPermissions"]`), whatever the size: to the maintainer *"Questa sessione è in modalità {mode}:
di notte ogni richiesta di permesso la ferma fino al mattino. Passa alla modalità auto prima di
andare."* (`en`: *"This session is in {mode} mode: at night every permission request stops it until
the morning. Switch to auto mode before you go."*); to the session, a context sentence saying the
same and not to start the unattended run until the mode is changed. When S2 applies too, one message
of two lines and one context of two sentences go out. A missing `permission_mode` counts as fine.

Messages to the maintainer follow `lang` (`en` by default, or `it`); context for the session is
English.

## 6. The rename hook (fallback path only)

UserPromptSubmit. It names a session, and the name is what a release door may trust, so it is a
guard: it is shown to the maintainer before install, with its tests. It acts only when all hold:
1. the prompt, stripped, is `/migrate <name>` (`<name>`: `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`);
2. a pending handoff exists for this folder and `<name>`;
3. this session is not already called `<name>`.

Then it looks for the holder: a registry file with `name == <name>`, the same `cwd`, a pid alive and
other than its own session's.
- No holder: output `sessionTitle: <name>`.
- Holder `idle`: SIGTERM, wait up to 5 s for the pid to go; gone, output `sessionTitle`; still
  there, no title and a context line saying so.
- Holder `busy` or `waiting`: no signal, no title; context: the old session is working, the
  maintainer closes it or waits, then types `/migrate <name>` again.

The skill has `disable-model-invocation: true`. What is left: a `/loop` prompt could type the same
words, and then only at a migration's moment (a pending handoff for that name). Written down, not
closed.

## 7. The script `crew.py`

`python3 -I <root>/scripts/crew.py <command>`, stdlib only, modules beside it, none over ~300 lines.
- `hook size`, `hook rename`, `hook start`: the three hooks; event JSON on stdin.
- `handoff save [--name ...]`: the body on stdin, writes the file of 4, prints its path. Refuses a
  body missing a section.
- `handoff status`: the pending handoffs of this folder, one line each.
- `migrate [name]`: name defaults to this session's. Prints the latest pending handoff for it, then
  the session's entry from `project.json`, then marks the handoff used. If a live session other than
  this one holds the name in this folder, it says so first (pid, status, size). No pending handoff:
  it runs `recover`.
- `recover [name]`: the latest transcript in this folder's project directory, other than its own,
  whose last `custom-title` is the name. Read from the end in chunks of 8 MB, never more than
  200 MB: the last compaction summary and the `user` and `assistant` text after it (text parts
  only, each cut at 2000 characters, 40 KB in all).
- `size [path]`: a transcript's size and what the size hook would say.

SessionStart (`hook start`), sources `startup` and `clear`: a pending handoff for this session's
name, or for this folder when the session has none, gives the session a context line and the
maintainer *"Passaggio in attesa per <name>: scrivi /migrate."* (or `/migrate <name>`).

## 8. The skills

- `skills/handoff/SKILL.md`: what goes in each section, the user's words quoted, nothing copied from
  memory; what the project's own guidelines ask for at a handoff; then
  `crew.py handoff save`; then tell the maintainer `/clear`, `/migrate`.
- `skills/migrate/SKILL.md`: `disable-model-invocation: true`, `argument-hint: [name]`; runs
  `crew.py migrate $ARGUMENTS`; summarises in at most ten lines: who the session is, the item under
  way, the next step; then starts from the handoff, not from the memory's whole index.

In a plugin skill's body Claude Code substitutes `${CLAUDE_PLUGIN_ROOT}` (documented); it is not an
environment variable of the Bash tool, so the skills write the full command with it in the body.

Frontmatter only uses fields both hosts read: `name` (equal to the folder), `description`,
`argument-hint`, `disable-model-invocation`.

## 9. Copilot in v1

The skills work as written, with `crew.py` called with `--name` and `--cwd`. Copilot ignores the
output of `userPromptSubmitted`, and has no `sessionTitle`: no size hook and no rename there in v1.
Its sessions are in `~/Library/Application Support/Code/User/workspaceStorage/<hash>/chatSessions/
<uuid>.jsonl`; a warning through `postToolUse` context is for after v1, once tried.

## 10. Tests

`python3 -I -m unittest discover -s tests`, stdlib only, every case in a temporary folder: fake
registry, fake transcripts, a fake status command, a real `sleep` child for SIGTERM. At least:
each row of section 5's tables, S2 and S3; each branch of section 6, including a peer-shaped prompt
that only contains `/migrate kcalloc` mid-text; `recover` on a transcript larger than one chunk with
the summary in an earlier chunk; `handoff save` refusing a missing section; `migrate` marking used
and never picking a used handoff.

## 11. Install

1. `/plugin marketplace add debug922/session-crew`, `/plugin install session-crew@session-crew`
   (from a clone: `/plugin marketplace add ./session-crew`).
2. If another size hook is already in `~/.claude/settings.json` under `UserPromptSubmit`, remove it
   (both would run).
3. Optionally write `~/.session-crew/<slug>/project.json` (section 4).
