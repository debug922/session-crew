# Changelog

## 0.1.0 (unreleased)

- Size hook: warns the session, then the user, when a transcript passes `warn_mb` and
  `tell_user_mb`; reminds the user of a pending handoff.
- Unattended nights: a size ceiling instead of a warning while a night runs, a warning when a night
  is started in a heavy session, and a warning when it is started in a permission mode that would
  stop it (N3).
- `/handoff` writes a handover under `~/.session-crew/<slug>/<name>/`; `/migrate` resumes it in a
  fresh conversation, or recovers from the old transcript after a crash.
- Rename hook for the new-tab fallback: gives a name to the new session, stopping an idle older
  session of the same name only when its start time checks out.
- SessionStart hook announces a pending handoff after `/clear`.
- Skills readable by GitHub Copilot in VS Code (script called by hand; no hooks there yet).
