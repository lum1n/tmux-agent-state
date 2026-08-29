# tmux-agent-state

TPM plugin: live AI-agent state on the tmux statusline, window list, and native session switcher (`prefix-s`).

Classification comes from [agent-watcher](https://github.com/lum1n/agent-watcher) (the same Python [sessh](https://github.com/lum1n/sessh) embeds over SSH). This repo pins that project as a git submodule under `vendor/agent-watcher` so you only add one plugin.

## Install

Add **after** continuum / other `status-right` plugins:

```tmux
set -g @plugin 'lum1n/tmux-agent-state'
```

Then `prefix-I`. Needs `python3`, `tmux` 3.2+, and `git` (first load runs `git submodule update --init` if TPM did not).

Local path install:

```tmux
set -g @plugin '/path/to/tmux-agent-state'
```

## States

`idle` · `thinking` · `running-tool` · `waiting-permission` · `errored`

Harnesses: Claude, Codex, OpenCode, Pi, Cursor. Agents must be running inside tmux.

## Surfaces

- **Status-right** — colored icon + text, e.g. `… thinking` or `⚠ needs you 2`. Empty when every agent is idle.
- **Window tabs** — colored icon only.
- **`prefix-s`** — icon + colored label on sessions and windows (`needs you`, `thinking`, `bash · ls`, …). This overrides the default session tree.

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

Per-window: `@agent_state`, `@agent_kind`, `@agent_glyph`, `@agent_color`, `@agent_label`. Per-session: `@agent_badge`, `@agent_glyph`, `@agent_label`, `@agent_worst`, `@agent_color`. Global: `@agent_needs_user`, `@agent_busy`, `@agent_thinking`, `@agent_running_tool`, `@agent_errored`.

The watcher listens on `#{socket_path}.agent-watcher.sock` (`0700`) and sets `@agent_watcher_socket`. Sessh attaches to that socket when present so the host does not run two classifiers.

## Updating the classifier

`agent-watcher` is maintained in its own repo. After you publish a new commit there:

```bash
git submodule update --remote vendor/agent-watcher
git add vendor/agent-watcher
git commit -m "Bump agent-watcher"
```
