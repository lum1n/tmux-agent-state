get_tmux_option() {
	local option=$1
	local default_value=$2
	local option_value
	option_value=$(tmux show-option -gqv "$option")
	if [ -z "$option_value" ]; then
		echo "$default_value"
	else
		echo "$option_value"
	fi
}

set_tmux_option() {
	local option=$1
	local value=$2
	tmux set-option -gq "$option" "$value"
}

option_on() {
	local value
	value=$(get_tmux_option "$1" "$2")
	case "$value" in
	on | true | 1 | yes) return 0 ;;
	*) return 1 ;;
	esac
}
