#!/usr/bin/env bash
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/utils/tmux.sh
source "$CURRENT_DIR/scripts/utils/tmux.sh"

decorate_windows() {
	option_on '@agent-state-windows' 'on' || return 0
	local fmt current old wrap repl
	# Color comes from @agent_color so a red ⚠ / yellow … reads in the tab list.
	wrap='#{?@agent_glyph, #[fg=#{@agent_color}]#{@agent_glyph}#[default],}'
	old='#{?@agent_glyph, #{@agent_glyph},}'
	for opt in window-status-format window-status-current-format; do
		fmt="$(tmux show-option -wgqv "$opt")"
		[ -n "$fmt" ] || continue
		case "$fmt" in
		*@agent_color*) continue ;;
		esac
		if [ "${fmt#*"$old"}" != "$fmt" ]; then
			current="${fmt//${old}/${wrap}}"
		else
			repl="#W${wrap}"
			current="${fmt//#W/${repl}}"
			if [ "$current" = "$fmt" ]; then
				current="${fmt}${wrap}"
			fi
		fi
		tmux set-option -wgq "$opt" "$current"
	done
}

inject_status() {
	option_on '@agent-state-status' 'on' || return 0
	local current script
	script="#(${CURRENT_DIR}/scripts/status.sh)"
	current="$(get_tmux_option 'status-right' '')"
	case "$current" in
	*"scripts/status.sh"*) return 0 ;;
	esac
	[ -n "$current" ] || current='#H '
	# Keep a trailing space so the segment does not glue to hostname.
	tmux set-option -gq status-right "${script} ${current}"
}

bind_choose_tree() {
	option_on '@agent-state-choose-tree' 'on' || return 0
	local key
	key="$(get_tmux_option '@agent-state-choose-key' 's')"
	tmux bind-key "$key" run-shell "$CURRENT_DIR/scripts/choose-tree.sh"
}

main() {
	"$CURRENT_DIR/scripts/run-watcher.sh"
	decorate_windows
	inject_status
	bind_choose_tree
}

main
