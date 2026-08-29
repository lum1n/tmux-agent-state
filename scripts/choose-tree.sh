#!/usr/bin/env bash
# Bound as prefix-s: icon + colored label on sessions and windows.
MARK='#{?@agent_glyph,#[fg=#{@agent_color}]#{@agent_glyph} #{@agent_label}#[default] ,}'
FORMAT="#{?pane_format,#{pane_current_command} \"#{pane_title}\",#{?window_format,${MARK}#{window_name}#{window_flags},${MARK}#{session_windows} windows#{?session_attached, (attached),}}}"

tmux choose-tree -Zs -F "$FORMAT"
