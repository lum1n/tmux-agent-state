# tmux-agent-state

TPM plugin: live AI-agent state on the tmux statusline, window list, and native session switcher (`prefix-s`).

Classification comes from the sibling [agent-watcher](../agent-watcher) package (the same Python sessh embeds over SSH). This repo only applies NDJSON onto tmux options and draws it.

## States

`idle` · `thinking` · `running-tool` · `waiting-permission` · `errored`

Harnesses: Claude, Codex, OpenCode, Pi, Cursor. Agents must be running inside tmux.

## Install

1. Clone [agent-watcher](../agent-watcher) next to this repo (or set `@agent-state-watcher`).
2. Add to `tmux.conf` **after** continuum / other `status-right` plugins:

```tmux
set -g @plugin '/home/vegard/repos/tmux-agent-state'
# or: set -g @plugin 'you/tmux-agent-state'
```

3. `prefix-I` (TPM) or `tmux source-file ~/.config/tmux/tmux.conf`.

Needs `python3` and `tmux` 3.2+.

## Surfaces

- **Status-right** — colored icon + text, e.g. `… thinking` or `⚠ needs you 2`. Empty when every agent is idle.
- **Window tabs** — colored icon only.
- **`prefix-s`** — icon + colored label on sessions and windows (`needs you`, `thinking`, `bash · ls`, …).

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
set -g @agent-state-watcher '/home/vegard/repos/agent-watcher/src/agent_watcher.py'
set -g @agent-state-status 'on'
set -g @agent-state-windows 'on'
set -g @agent-state-choose-tree 'on'
set -g @agent-state-choose-key 's'
set -g @agent-state-glyphs '⚠ ✖ ⚙ …'
set -g @agent-state-colors 'red red cyan yellow'
```

Per-window options the plugin writes: `@agent_state`, `@agent_kind`, `@agent_glyph`, `@agent_color`, `@agent_label`. Per-session: `@agent_badge`, `@agent_glyph`, `@agent_label`, `@agent_worst`, `@agent_color`. Global: `@agent_needs_user`, `@agent_busy`, `@agent_thinking`, `@agent_running_tool`, `@agent_errored`.

The watcher also listens on `#{socket_path}.agent-watcher.sock` (`0700`) and publishes the path as `@agent_watcher_socket`. [Sessh](../sessh) attaches to that socket when present so the host does not run two classifiers.
