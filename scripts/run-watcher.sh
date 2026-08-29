#!/usr/bin/env bash
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=utils/tmux.sh
source "$CURRENT_DIR/utils/tmux.sh"

resolve_watcher() {
	local configured sibling home_copy
	configured="$(get_tmux_option '@agent-state-watcher' '')"
	if [ -n "$configured" ] && [ -f "$configured" ]; then
		printf '%s\n' "$configured"
		return 0
	fi
	sibling="$(cd "$CURRENT_DIR/../.." && pwd)/agent-watcher/src/agent_watcher.py"
	if [ -f "$sibling" ]; then
		printf '%s\n' "$sibling"
		return 0
	fi
	home_copy="${HOME}/repos/agent-watcher/src/agent_watcher.py"
	if [ -f "$home_copy" ]; then
		printf '%s\n' "$home_copy"
		return 0
	fi
	tmux display-message "tmux-agent-state: agent-watcher not found (set @agent-state-watcher)"
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
