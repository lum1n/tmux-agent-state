#!/usr/bin/env bash
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$CURRENT_DIR/.." && pwd)"
# shellcheck source=utils/tmux.sh
source "$CURRENT_DIR/utils/tmux.sh"

# status-interval calls --kick: never block the bar on git or flash a message.
KICK=0
[ "${1:-}" = "--kick" ] && KICK=1

ensure_submodule() {
	local watcher="$PLUGIN_ROOT/vendor/agent-watcher/src/agent_watcher.py"
	[ -f "$watcher" ] && return 0
	[ "$KICK" -eq 1 ] && return 1
	[ -f "$PLUGIN_ROOT/.gitmodules" ] || return 1
	command -v git >/dev/null 2>&1 || return 1
	git -C "$PLUGIN_ROOT" submodule update --init --depth 1 vendor/agent-watcher >/dev/null 2>&1
}

resolve_watcher() {
	local configured vendor sibling
	configured="$(get_tmux_option '@agent-state-watcher' '')"
	if [ -n "$configured" ] && [ -f "$configured" ]; then
		printf '%s\n' "$configured"
		return 0
	fi
	ensure_submodule || true
	vendor="$PLUGIN_ROOT/vendor/agent-watcher/src/agent_watcher.py"
	if [ -f "$vendor" ]; then
		printf '%s\n' "$vendor"
		return 0
	fi
	# Local checkout next to this repo (plugin author / sessh sibling).
	sibling="$(cd "$PLUGIN_ROOT/.." && pwd)/agent-watcher/src/agent_watcher.py"
	if [ -f "$sibling" ]; then
		printf '%s\n' "$sibling"
		return 0
	fi
	[ "$KICK" -eq 0 ] && tmux display-message "tmux-agent-state: agent-watcher missing (git submodule update --init)"
	return 1
}

start_watcher() {
	local watcher logfile socket
	watcher="$(resolve_watcher)" || return 1
	socket="$(tmux display-message -p '#{socket_path}')"
	[ -n "$socket" ] || return 1
	logfile="${socket}.agent-state.log"
	python3 "$CURRENT_DIR/manage_watcher.py" \
		--watcher "$watcher" \
		--socket "$socket" \
		>>"$logfile" 2>&1
}

start_watcher
