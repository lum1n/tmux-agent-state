#!/usr/bin/env bash
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=utils/tmux.sh
source "$CURRENT_DIR/utils/tmux.sh"

# Continuum-style keep-alive: status-interval restarts a dead daemon.
"$CURRENT_DIR/run-watcher.sh" --kick >/dev/null 2>&1 || true

glyphs="$(get_tmux_option '@agent-state-glyphs' '⚠ ✖ ⚙ …')"
colors="$(get_tmux_option '@agent-state-colors' 'red red cyan yellow')"
# shellcheck disable=SC2086
set -- $glyphs
perm="${1:-⚠}"
err="${2:-✖}"
tool="${3:-⚙}"
think="${4:-…}"
# shellcheck disable=SC2086
set -- $colors
perm_fg="${1:-red}"
err_fg="${2:-red}"
tool_fg="${3:-cyan}"
think_fg="${4:-yellow}"

needs="$(tmux show-option -gqv @agent_needs_user)"
errored="$(tmux show-option -gqv @agent_errored)"
running="$(tmux show-option -gqv @agent_running_tool)"
thinking="$(tmux show-option -gqv @agent_thinking)"
needs="${needs:-0}"
errored="${errored:-0}"
running="${running:-0}"
thinking="${thinking:-0}"

segment() {
	local fg="$1" icon="$2" word="$3" n="$4" bold="$5"
	[ "$n" -gt 0 ] 2>/dev/null || return 0
	local style="fg=${fg}"
	[ "$bold" = "1" ] && style="${style},bold"
	if [ "$n" -gt 1 ]; then
		printf '#[%s]%s %s %d#[default]' "$style" "$icon" "$word" "$n"
	else
		printf '#[%s]%s %s#[default]' "$style" "$icon" "$word"
	fi
}

parts=()
seg="$(segment "$perm_fg" "$perm" "needs you" "$needs" 1)"
[ -n "$seg" ] && parts+=("$seg")
seg="$(segment "$err_fg" "$err" "error" "$errored" 1)"
[ -n "$seg" ] && parts+=("$seg")
seg="$(segment "$tool_fg" "$tool" "tool" "$running" 0)"
[ -n "$seg" ] && parts+=("$seg")
seg="$(segment "$think_fg" "$think" "thinking" "$thinking" 0)"
[ -n "$seg" ] && parts+=("$seg")

if [ "${#parts[@]}" -eq 0 ]; then
	exit 0
fi
printf '%s \n' "${parts[*]}"
