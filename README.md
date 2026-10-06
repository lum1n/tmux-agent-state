# tmux-agent-state

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

TPM plugin: live AI-agent state on the tmux statusline, window list, and native session switcher (`prefix-s`).

Classification comes from [agent-watcher](https://github.com/lum1n/agent-watcher). This repo pins that project as a git submodule under `vendor/agent-watcher` so you only add one plugin.

## Install

Add **after** continuum / other `status-right` plugins:

```tmux
set -g @plugin 'lum1n/tmux-agent-state'
```

Then `prefix-I`. Requires `python3` 3.10+, `tmux` 3.2+, and `git` (first load runs `git submodule update --init` if TPM did not).

Local path:

```tmux
set -g @plugin '/path/to/tmux-agent-state'
```

## States

`idle` · `thinking` · `running-tool` · `waiting-permission` · `errored`

Harnesses: Claude, Codex, OpenCode, Pi, Cursor, Copilot. Agents must be running inside tmux.

## Surfaces

- **Status-right** — colored icon + text across all sessions, e.g. `… thinking` or `⚠ needs you 2`. Empty when every agent is idle.
- **Window tabs** — colored icon only on the window that has the agent.
- **`prefix-s`** — icon + colored label on sessions and windows. This **replaces** the default session tree. Set `@agent-state-choose-tree off` to keep stock `choose-tree`.

## Icons and colors

| State | Icon | Color |
| --- | --- | --- |
| waiting-permission | ⚠ | red (bold on the statusline) |
| errored | ✖ | red |
| running-tool | ⚙ | cyan |
| thinking | … | yellow |
| idle / unbound | (none) | — |

## Options

```tmux
# set -g @agent-state-watcher '/custom/path/agent_watcher.py'
set -g @agent-state-status 'on'
set -g @agent-state-windows 'on'
set -g @agent-state-choose-tree 'on'
set -g @agent-state-choose-key 's'
set -g @agent-state-glyphs '⚠ ✖ ⚙ …'
set -g @agent-state-colors 'red red cyan yellow'
```

Per-window: `@agent_state`, `@agent_kind`, `@agent_glyph`, `@agent_color`, `@agent_label`. Per-session: `@agent_badge`, `@agent_label`, `@agent_worst`, `@agent_color`. Global: `@agent_needs_user`, `@agent_busy`, `@agent_thinking`, `@agent_running_tool`, `@agent_errored`.

The watcher listens on `#{socket_path}.agent-watcher.sock` (mode `0700`, same uid) and sets `@agent_watcher_socket`. Other local clients can attach to that socket so the host does not run two classifiers.

If the daemon exits, the next `status-interval` refresh starts it again. Plugin reloads and status refreshes also restart it automatically when the plugin adapter, classifier Python files, or resolved `@agent-state-watcher` path change. Existing daemons from older plugin versions are restarted on the first check after upgrading. Keep `status-interval` above 0.

Lifecycle checks use a crash-safe exclusive lock and verify process ownership and identity before signalling a PID. Commands use argument lists rather than shell interpolation (ASVS 15.4.1, 15.4.3, and 1.2.5).

The watcher reads pane text on this machine only. The listen socket is mode `0700` (your uid). Nothing is sent off-host.

## Updating the classifier

`agent-watcher` is maintained in its own repo. After you publish a new commit there:

```bash
git submodule update --remote vendor/agent-watcher
git add vendor/agent-watcher
git commit -m "Bump agent-watcher"
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| No icons | Agent must be a pane in this tmux server. `tmux show -gqv @agent_watcher_socket` should be a path. |
| Daemon died | Log is `#{socket_path}.agent-state.log` (often `/tmp/tmux-$UID/default.agent-state.log`). Reload: `tmux run-shell ~/.tmux/plugins/tmux-agent-state/agent-state.tmux`. |
| `agent-watcher missing` | `git -C ~/.tmux/plugins/tmux-agent-state submodule update --init` (or your local clone path). |
| `prefix-s` looks stock | Another plugin may have rebound `s`. Set `@agent-state-choose-key`, or `@agent-state-choose-tree off` to keep the default tree. |
| Every tab has the same icon | Pull 0.1.0+; older checkouts set session `@agent_glyph`, which window-status inherits. |

## License

MIT. See [LICENSE](LICENSE).
