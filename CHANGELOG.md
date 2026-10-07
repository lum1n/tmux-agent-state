# Changelog

## 0.2.0

- Bump agent-watcher: lower polling CPU and subscription quota events on the
  listen socket (replayed to new subscribers).
- Quota probes read local agent logins and call vendor usage APIs; disable
  with `set -g @agent-state-quota 'off'`. Changing the option restarts the
  daemon on the next status refresh.
- Coalesce bursts of watcher events into one tmux write and skip writes that
  would not change the status bar, tabs, or tree.

## 0.1.3

- Automatically restart the daemon after plugin/classifier updates or watcher path changes, including upgrades from older plugin versions.
- Serialize daemon lifecycle checks with a crash-safe lock and verify process identity before stopping a recorded PID.

## 0.1.2

- Bump [agent-watcher](https://github.com/lum1n/agent-watcher) to pick up GitHub Copilot CLI discover and classify.

## 0.1.1

- Do not register tmux hooks. 3.7b rejects named hooks (`session-created[…]`); respawn stays on `status-interval`.

## 0.1.0

- Statusline, window tabs, and `prefix-s` show live agent state.
- Pins [agent-watcher](https://github.com/lum1n/agent-watcher) as a submodule.
- Host Unix socket so another local client can share the classifier.
- Window glyphs are scoped to the agent window only.
- Watcher respawns if the daemon exits (checked on each `status-interval`).
