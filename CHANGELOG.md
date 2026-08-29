# Changelog

## 0.1.0

- Statusline, window tabs, and `prefix-s` show live agent state.
- Pins [agent-watcher](https://github.com/lum1n/agent-watcher) as a submodule.
- Host Unix socket for Sessh so the classifier is not started twice.
- Window glyphs are scoped to the agent window only.
- Watcher respawns if the daemon exits (status-interval + named attach hooks).
