#!/usr/bin/env bash
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$CURRENT_DIR/.." && pwd)"
# shellcheck source=utils/tmux.sh
source "$CURRENT_DIR/utils/tmux.sh"

ensure_submodule() {
	local watcher="$PLUGIN_ROOT/vendor/agent-watcher/src/agent_watcher.py"
	[ -f "$watcher" ] && return 0
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
	tmux display-message "tmux-agent-state: agent-watcher missing (git submodule update --init)"
	return 1
}

start_watcher() {
	local watcher pidfile logfile socket pid
	watcher="$(resolve_watcher)" || return 1
	socket="$(tmux display-message -p '#{socket_path}')"
	pidfile="${socket}.agent-state.pid"
	logfile="${socket}.agent-state.log"
	if [ -f "$pidfile" ]; then
		pid="$(cat "$pidfile")"
		if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
			return 0
		fi
	fi
	nohup env PYTHONUNBUFFERED=1 python3 -u "$CURRENT_DIR/apply_tmux.py" \
		--watcher "$watcher" \
		--socket "$socket" \
		>>"$logfile" 2>&1 &
	echo $! >"$pidfile"
}

start_watcher
