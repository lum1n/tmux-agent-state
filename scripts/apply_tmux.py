#!/usr/bin/env python3
"""Read agent-watcher NDJSON and write tmux @agent_* options."""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
from typing import Any

RANK = {
    "waiting-permission": 50,
    "errored": 40,
    "running-tool": 30,
    "thinking": 20,
    "unbound": 10,
    "idle": 0,
}

DEFAULT_GLYPHS = {
    "waiting-permission": "⚠",
    "errored": "✖",
    "running-tool": "⚙",
    "thinking": "…",
}

DEFAULT_COLORS = {
    "waiting-permission": "red",
    "errored": "red",
    "running-tool": "cyan",
    "thinking": "yellow",
}

DEFAULT_GLYPHS_OPT = "⚠ ✖ ⚙ …"
DEFAULT_COLORS_OPT = "red red cyan yellow"

WINDOW_OPTS = (
    "@agent_state",
    "@agent_kind",
    "@agent_glyph",
    "@agent_color",
    "@agent_label",
    "@agent_tool",
    "@agent_summary",
)
SESSION_OPTS = (
    "@agent_badge",
    "@agent_worst",
    "@agent_color",
    "@agent_label",
)
GLOBAL_OPTS = (
    "@agent_needs_user",
    "@agent_busy",
    "@agent_thinking",
    "@agent_running_tool",
    "@agent_errored",
)

LABEL = {
    "waiting-permission": "needs you",
    "errored": "error",
    "running-tool": "tool",
    "thinking": "thinking",
    "unbound": "",
    "idle": "",
}


def _parse_four(raw: str, defaults: dict[str, str]) -> dict[str, str]:
    parts = (raw or "").split()
    keys = ("waiting-permission", "errored", "running-tool", "thinking")
    out = dict(defaults)
    for i, key in enumerate(keys):
        if i < len(parts) and parts[i]:
            out[key] = parts[i]
    return out


def parse_glyphs(raw: str) -> dict[str, str]:
    return _parse_four(raw, DEFAULT_GLYPHS)


def parse_colors(raw: str) -> dict[str, str]:
    return _parse_four(raw, DEFAULT_COLORS)


def glyph_for(state: str, glyphs: dict[str, str]) -> str:
    return glyphs.get(state, "")


def color_for(state: str, colors: dict[str, str]) -> str:
    return colors.get(state, "")


def label_for(row: dict[str, Any]) -> str:
    state = row.get("state") or ("unbound" if row.get("unbound") else "idle")
    if state == "running-tool":
        tool = (row.get("toolName") or "tool").strip()
        target = (row.get("toolTarget") or "").strip()
        if len(target) > 40:
            target = target[:39] + "…"
        return f"{tool} · {target}" if target else tool
    return LABEL.get(state, "")


def agent_key(session: str, window: int) -> str:
    return "%s:w%d" % (session, window)


class Tmux:
    def __init__(self, socket: str | None) -> None:
        self.cmd = ["tmux"]
        if socket:
            self.cmd.extend(["-S", socket])

    def alive(self) -> bool:
        try:
            subprocess.check_output(
                self.cmd + ["list-sessions"],
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def show_global(self, option: str, default: str = "") -> str:
        try:
            out = subprocess.check_output(
                self.cmd + ["show-option", "-gqv", option],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return out.rstrip("\n") or default
        except Exception:
            return default

    def run(self, batches: list[list[str]]) -> None:
        chunk: list[list[str]] = []
        for part in batches:
            chunk.append(part)
            if len(chunk) >= 24:
                self._run_chunk(chunk)
                chunk = []
        if chunk:
            self._run_chunk(chunk)

    def _run_chunk(self, chunk: list[list[str]]) -> None:
        args = list(self.cmd)
        for i, part in enumerate(chunk):
            if i:
                args.append(";")
            args.extend(part)
        try:
            subprocess.check_call(args, stderr=subprocess.DEVNULL)
        except Exception as e:
            print("tmux batch failed: %s" % e, file=sys.stderr)

    def refresh(self) -> None:
        try:
            subprocess.check_call(
                self.cmd + ["refresh-client", "-S"],
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def window_target(session: str, window: int) -> str:
    return "=%s:%d" % (session, window)


def session_target(session: str) -> str:
    # set-option -t does not accept the '=' exact-match prefix (it looks
    # for a session literally named "=foo"). Window targets still use '='.
    return session


def sanitize(value: Any, limit: int = 80) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def set_user_opt(
    batches: list[list[str]],
    scope: list[str],
    name: str,
    value: str,
) -> None:
    """Set a @user option, or unset it when empty (tmux rejects '')."""
    if value:
        batches.append(scope + [name, value])
        return
    unset = list(scope)
    flags = unset[1] if len(unset) > 1 else ""
    if flags in ("-g", "-w", "-s", "-gw", "-wg", "-gs", "-sg"):
        unset[1] = flags + "u"
    else:
        unset.insert(1, "-u")
    batches.append(unset + [name])


def apply_event(store: dict[str, dict[str, Any]], ev: dict[str, Any]) -> bool:
    typ = ev.get("type")
    if typ == "snapshot":
        store.clear()
        for agent in ev.get("agents") or []:
            if not isinstance(agent, dict):
                continue
            session = agent.get("session")
            window = agent.get("window")
            if not isinstance(session, str) or not session:
                continue
            try:
                window = int(window)
            except Exception:
                continue
            store[agent_key(session, window)] = agent
        return True
    if typ in ("state", "unbound"):
        session = ev.get("session")
        window = ev.get("window")
        try:
            window = int(window)
        except Exception:
            return False
        if not isinstance(session, str) or not session:
            return False
        row = dict(ev)
        if typ == "unbound":
            row["unbound"] = True
            row.setdefault("state", "idle")
        store[agent_key(session, window)] = row
        return True
    if typ == "gone":
        session = ev.get("session")
        try:
            window = int(ev.get("window"))
        except Exception:
            return False
        if not isinstance(session, str):
            return False
        return store.pop(agent_key(session, window), None) is not None
    return False


def load_style(tmux: Tmux) -> tuple[dict[str, str], dict[str, str]]:
    glyphs = parse_glyphs(
        tmux.show_global("@agent-state-glyphs", DEFAULT_GLYPHS_OPT)
    )
    colors = parse_colors(
        tmux.show_global("@agent-state-colors", DEFAULT_COLORS_OPT)
    )
    return glyphs, colors


def write_tmux(
    tmux: Tmux,
    store: dict[str, dict[str, Any]],
    glyphs: dict[str, str],
    colors: dict[str, str],
    prev_windows: set[tuple[str, int]],
    prev_sessions: set[str],
) -> tuple[set[tuple[str, int]], set[str]]:
    by_session: dict[str, list[dict[str, Any]]] = {}
    windows: set[tuple[str, int]] = set()
    batches: list[list[str]] = []

    for row in store.values():
        session = row.get("session")
        try:
            window = int(row.get("window"))
        except Exception:
            continue
        if not isinstance(session, str):
            continue
        windows.add((session, window))
        state = row.get("state") or ("unbound" if row.get("unbound") else "idle")
        kind = row.get("kind") or ""
        glyph = glyph_for(state, glyphs)
        label = label_for({**row, "state": state})
        target = window_target(session, window)
        wset = ["set-option", "-w", "-t", target]
        set_user_opt(batches, wset, "@agent_state", state)
        set_user_opt(batches, wset, "@agent_kind", kind)
        set_user_opt(batches, wset, "@agent_glyph", glyph)
        set_user_opt(batches, wset, "@agent_color", color_for(state, colors))
        set_user_opt(batches, wset, "@agent_label", label)
        set_user_opt(batches, wset, "@agent_tool", sanitize(row.get("toolName"), 40))
        set_user_opt(
            batches, wset, "@agent_summary", sanitize(row.get("summary"), 80)
        )
        by_session.setdefault(session, []).append({**row, "state": state})

    for session, rows in by_session.items():
        states = [r.get("state") or "idle" for r in rows]
        worst = max(states, key=lambda s: RANK.get(s, 0))
        glyph = glyph_for(worst, glyphs)
        count = sum(1 for s in states if s == worst)
        if count > 1:
            session_label = "%s · %d" % (LABEL.get(worst) or worst, count)
        else:
            worst_row = next(
                (r for r in rows if (r.get("state") or "idle") == worst),
                {"state": worst},
            )
            session_label = label_for(worst_row)
        target = session_target(session)
        sset = ["set-option", "-t", target]
        set_user_opt(batches, sset, "@agent_badge", glyph)
        # Never set session @agent_glyph — window-status inherits it and
        # paints every tab in the session.
        batches.append(["set-option", "-u", "-t", target, "@agent_glyph"])
        set_user_opt(batches, sset, "@agent_label", session_label)
        set_user_opt(batches, sset, "@agent_worst", worst if glyph else "")
        set_user_opt(
            batches, sset, "@agent_color", color_for(worst, colors) if glyph else ""
        )

    needs = sum(
        1 for r in store.values() if r.get("state") == "waiting-permission"
    )
    errored = sum(1 for r in store.values() if r.get("state") == "errored")
    thinking = sum(1 for r in store.values() if r.get("state") == "thinking")
    running = sum(1 for r in store.values() if r.get("state") == "running-tool")
    batches.append(["set-option", "-g", "@agent_needs_user", str(needs)])
    batches.append(["set-option", "-g", "@agent_busy", str(thinking + running)])
    batches.append(["set-option", "-g", "@agent_thinking", str(thinking)])
    batches.append(["set-option", "-g", "@agent_running_tool", str(running)])
    batches.append(["set-option", "-g", "@agent_errored", str(errored)])

    for session, window in prev_windows - windows:
        target = window_target(session, window)
        for opt in WINDOW_OPTS:
            batches.append(["set-option", "-wu", "-t", target, opt])

    sessions = set(by_session)
    for session in prev_sessions - sessions:
        target = session_target(session)
        for opt in SESSION_OPTS:
            batches.append(["set-option", "-u", "-t", target, opt])

    tmux.run(batches)
    return windows, sessions


def parse_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        ev = json.loads(line)
    except Exception:
        return None
    return ev if isinstance(ev, dict) else None


def _self_test() -> int:
    glyphs = parse_glyphs(DEFAULT_GLYPHS_OPT)
    colors = parse_colors(DEFAULT_COLORS_OPT)
    assert glyph_for("waiting-permission", glyphs) == "⚠"
    assert color_for("thinking", colors) == "yellow"
    assert glyph_for("idle", glyphs) == ""
    assert sanitize("a\nb  c") == "a b c"
    store: dict[str, dict[str, Any]] = {}
    assert apply_event(
        store,
        {
            "type": "state",
            "session": "dev",
            "window": 2,
            "kind": "claude",
            "state": "thinking",
        },
    )
    assert store["dev:w2"]["state"] == "thinking"
    assert apply_event(store, {"type": "gone", "session": "dev", "window": 2})
    assert store == {}
    assert apply_event(
        store,
        {
            "type": "snapshot",
            "agents": [
                {"session": "a", "window": 1, "kind": "pi", "state": "idle"},
                {"session": "a", "window": "2", "kind": "claude", "state": "errored"},
            ],
        },
    )
    assert set(store) == {"a:w1", "a:w2"}
    assert label_for({"state": "running-tool", "toolName": "bash", "toolTarget": "ls"}) == "bash · ls"
    print("ok  apply_tmux self-test")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watcher", default="")
    parser.add_argument("--socket", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not args.watcher:
        parser.error("--watcher is required")

    tmux = Tmux(args.socket or None)
    store: dict[str, dict[str, Any]] = {}
    prev_windows: set[tuple[str, int]] = set()
    prev_sessions: set[str] = set()

    listen = ""
    if args.socket:
        listen = args.socket + ".agent-watcher.sock"
    cmd = [sys.executable, "-u", args.watcher]
    if listen:
        cmd.extend(["--listen", listen])
    print("apply_tmux starting watcher %s" % args.watcher, file=sys.stderr)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    published = False
    try:
        for line in proc.stdout:
            if not tmux.alive():
                print("tmux server gone", file=sys.stderr)
                break
            ev = parse_line(line)
            if ev and ev.get("type") == "hello" and listen and not published:
                tmux.run(
                    [["set-option", "-g", "@agent_watcher_socket", listen]]
                )
                published = True
                print("listening %s" % listen, file=sys.stderr)
            if not ev:
                continue
            if not apply_event(store, ev):
                continue
            glyphs, colors = load_style(tmux)
            prev_windows, prev_sessions = write_tmux(
                tmux, store, glyphs, colors, prev_windows, prev_sessions
            )
            tmux.refresh()
    except Exception as e:
        print("apply_tmux crashed: %s" % e, file=sys.stderr)
        raise
    finally:
        if published:
            tmux.run([["set-option", "-gu", "@agent_watcher_socket"]])
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
        print("watcher exit %s" % proc.returncode, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
