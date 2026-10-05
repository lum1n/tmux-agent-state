# Changelog

## Unreleased

- Bump [agent-watcher](https://github.com/lum1n/agent-watcher) to pick up GitHub Copilot CLI discover and classify.

## 0.1.1

- Do not register tmux hooks. 3.7b rejects named hooks (`session-created[…]`); respawn stays on `status-interval`.

## 0.1.0

- Statusline, window tabs, and `prefix-s` show live agent state.
- Pins [agent-watcher](https://github.com/lum1n/agent-watcher) as a submodule.
- Host Unix socket so another local client can share the classifier.
- Window glyphs are scoped to the agent window only.
- Watcher respawns if the daemon exits (checked on each `status-interval`).
