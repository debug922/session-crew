---
name: setup
description: Make or change this project's session-crew configuration in chat, with options to choose from: language, sizes, nights, sessions, the linked git repositories with who pushes them, their checks and tags, the commit rules. Use when the user asks to set up, configure or change the project's workflow.
argument-hint: ""
---

# /setup

Make the project's configuration (`~/.session-crew/<slug>/project.json`) with the user, in chat. The
file decides who may push which repository, so the write is the last step and the user confirms it.
Nothing is written before it. Say each time what you found and ask only what you did not.

Every command below runs the plugin's script:
`python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" ...`

## 1. What is there

1. Run `... config discover` (JSON) and `... config show`. `discover` lists the git repositories
   under the folder (two levels) and those the table already names elsewhere, each with its origin,
   its GitHub name and whether GitHub holds it `private`, `public` or `unknown` (GitHub could not be
   asked); the sessions the user has named in this folder; the current file.
2. Show the current configuration as a short table, then what you found. Offer what you found for
   confirmation; never ask again what the file or the discovery already tells you.
3. A repository whose origin is not GitHub's (`github` is null) cannot be linked: say so and go on.
   A repository with no origin cannot either. A visibility `unknown` is asked of the user.

## 2. Questions, in rounds

Under Claude Code ask with the AskUserQuestion tool: at most 4 questions a call, 2 to 4 options each,
the free answer "Other" is always there. Put the current value or the likeliest choice first, marked
"(current)" or "(recommended)". Under Copilot (no option tool) ask the same rounds as numbered lists
and let the user answer with the number. If a question comes back unanswered (the tool's timeout),
stop: write nothing and say where you stopped.

Rounds, skipping what is already settled:

- **General**: the language of the messages to the user (`it`, `en`); the two sizes (`warn_mb` 400
  and `tell_user_mb` 800 by default; options such as 400/800, 200/400, 800/1000); whether nights are
  used (an unattended run; then ask for the status command as an argument list, the pattern its
  output matches, and the phrase that starts a night; without nights write no `unattended` block);
  the commit rules: none, no co-author trailer, no long or medium dash, or both. In the draft the
  two dashes (U+2013 and U+2014) go into `forbid` as JSON unicode escapes, never as the characters
  themselves.
- **Sessions**: for each session found, its role in a line and the mains it owns (free answer; an
  option "no entry" is fine). A session not found can be added by name.
- **Repositories**, one question each, four to a call: linked and pushed by which session (an option
  per named session, "unchanged" first when the table has it, "not linked"). A repository pushed by
  nobody is linked with an empty `pushers`: its push stays the user's.
- **Checks and tags** for each linked repository, two questions each:
  - checks before its push: none (the messages are judged by the commit rules anyway), a preset
    (`go`: vet, test, govulncheck; `unittest`: `python3 -I -m unittest discover -s tests`;
    `frontend`: typecheck and tests when `frontend/` changed), or a command of its own as an
    argument list (`{"run": ["make", "test"]}`, optionally `"in"`, `"when_changed"`, `"in_repo"`);
  - its tags: the user's (`"tags": null`), or through the door with the version written in
    `CHANGELOG.md` (`"changelog"`) or in `VERSION` (`"file"`), annotated or not.

## 3. The summary, the draft and the write

1. Say what changes against the current file, field by field and repository by repository, in plain
   words. Wait for the user to agree.
2. Write the whole new file (not a patch) as JSON to `<drafts_dir>/setup.json`, the `drafts_dir`
   that `discover` printed. Use the Write tool. Fields: `lang`, `warn_mb`, `tell_user_mb`,
   `unattended`, `sessions`, `commit_rules`, `repos` (each: `name`, `path`, `github`, `visibility`
   `private` or `public`, `pushers`, `checks`, `tags`). Keep every field of the current file that
   the user did not change, the unknown ones too.
3. Under Claude Code run `... config apply setup.json`. The plugin's guard asks the user before it
   runs (and refuses it while a night is on); the script validates the draft, prints the changes,
   keeps the previous file as `project.json.prev` and writes. If it refuses the draft, fix the draft
   from its message and run it again. Never write `project.json` by any other way.
4. Under Copilot there is no guard to stand between you and the write: do not run `config apply`.
   Print the line (`python3 -I /path/to/scripts/crew.py config apply setup.json --cwd <folder>`) and
   tell the user to run it in his own terminal, where the script asks for a typed `yes`.
5. Tell the user what was written and that `/push <repo>` and `/release <repo> vX.Y.Z` now work for
   the sessions named as pushers.
