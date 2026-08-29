#!/usr/bin/env bash
# Window rows use window-scoped @agent_glyph (only the pane that has an agent).
# Session rows use @agent_badge so we do not inherit a glyph onto every tab.
WIN='#{?@agent_glyph,#[fg=#{@agent_color}]#{@agent_glyph} #{@agent_label}#[default] ,}'
SESS='#{?@agent_badge,#[fg=#{@agent_color}]#{@agent_badge} #{@agent_label}#[default] ,}'
FORMAT="#{?pane_format,#{pane_current_command} \"#{pane_title}\",#{?window_format,${WIN}#{window_name}#{window_flags},${SESS}#{session_windows} windows#{?session_attached, (attached),}}}"

tmux choose-tree -Zs -F "$FORMAT"
