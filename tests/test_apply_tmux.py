import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apply_tmux", ROOT / "scripts/apply_tmux.py")
apply_tmux = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_tmux)

# Records every call; answers show-option from $FAKE_TMUX_QUOTA and fails
# list-sessions when $FAKE_TMUX_DEAD is set.
FAKE_TMUX = """\
#!/bin/sh
printf '%s\\n' "$*" >>"$FAKE_TMUX_LOG"
case "$*" in
*"show-option -gqv @agent-state-quota"*) printf '%s\\n' "$FAKE_TMUX_QUOTA" ;;
*list-sessions*) [ -z "$FAKE_TMUX_DEAD" ] || exit 1 ;;
esac
exit 0
"""

WATCHER = """\
import json
import sys
import time

with open(sys.argv[0] + ".argv", "w") as out:
    json.dump(sys.argv[1:], out)

def emit(*events):
    # One write per line: drain_stdout selects on the fd, so lines that
    # arrive in a single write sit in the reader's buffer uncoalesced.
    for ev in events:
        sys.stdout.write(json.dumps(ev) + "\\n")
        sys.stdout.flush()
        time.sleep(0.02)

def state(name, **extra):
    return {"type": "state", "session": "dev", "window": 1, "kind": "claude",
            "state": name, **extra}

emit({"type": "hello"}, state("thinking"), state("running-tool", toolName="bash"),
     state("thinking"))
time.sleep(0.4)
emit(state("thinking"))
time.sleep(0.4)
emit(state("waiting-permission"))
time.sleep(0.4)
"""


def state_row(state, **extra):
    return {"session": "dev", "window": 1, "kind": "claude", "state": state, **extra}


class VisualFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.glyphs = apply_tmux.parse_glyphs(apply_tmux.DEFAULT_GLYPHS_OPT)
        self.colors = apply_tmux.parse_colors(apply_tmux.DEFAULT_COLORS_OPT)

    def fp(self, store, glyphs=None, colors=None):
        return apply_tmux.visual_fingerprint(
            store, glyphs or self.glyphs, colors or self.colors)

    def test_invisible_fields_do_not_change_fingerprint(self):
        before = self.fp({"dev:w1": state_row("thinking", ts=1, pid=10)})
        after = self.fp({"dev:w1": state_row("thinking", ts=2, pid=11)})
        self.assertEqual(before, after)

    def test_visible_fields_change_fingerprint(self):
        base = self.fp({"dev:w1": state_row("running-tool", toolName="bash")})
        for row in (
            state_row("thinking"),
            state_row("running-tool", toolName="edit"),
            state_row("running-tool", toolName="bash", toolTarget="ls"),
            state_row("running-tool", toolName="bash", summary="listing"),
            {**state_row("running-tool", toolName="bash"), "kind": "pi"},
        ):
            with self.subTest(row=row):
                self.assertNotEqual(base, self.fp({"dev:w1": row}))

    def test_whitespace_only_summary_change_is_ignored(self):
        before = self.fp({"dev:w1": state_row("idle", summary="a  b")})
        after = self.fp({"dev:w1": state_row("idle", summary="a\nb")})
        self.assertEqual(before, after)

    def test_unbound_without_state_differs_from_idle(self):
        idle = self.fp({"dev:w1": state_row(None)})
        unbound = self.fp({"dev:w1": {**state_row(None), "unbound": True}})
        self.assertNotEqual(idle, unbound)
        self.assertEqual(idle[0][0][1], "idle")
        self.assertEqual(unbound[0][0][1], "unbound")

    def test_style_change_changes_fingerprint(self):
        store = {"dev:w1": state_row("thinking")}
        glyphs = apply_tmux.parse_glyphs("! x > *")
        colors = apply_tmux.parse_colors("red red blue magenta")
        self.assertNotEqual(self.fp(store), self.fp(store, glyphs=glyphs))
        self.assertNotEqual(self.fp(store), self.fp(store, colors=colors))

    def test_order_independent_and_tracks_window_set(self):
        a = state_row("thinking")
        b = {**state_row("errored"), "window": 2}
        self.assertEqual(self.fp({"dev:w1": a, "dev:w2": b}),
                         self.fp({"dev:w2": b, "dev:w1": a}))
        self.assertNotEqual(self.fp({"dev:w1": a}), self.fp({"dev:w1": a, "dev:w2": b}))
        self.assertNotEqual(self.fp({"dev:w1": a}), self.fp({}))

    def test_global_counts(self):
        store = {
            "a:w1": state_row("waiting-permission"),
            "a:w2": state_row("errored"),
            "a:w3": state_row("thinking"),
            "a:w4": state_row("running-tool"),
            "a:w5": state_row("running-tool"),
            "a:w6": state_row("idle"),
        }
        self.assertEqual(self.fp(store)[1:], (1, 1, 1, 2))


class DrainStdoutTests(unittest.TestCase):
    def setUp(self):
        read_fd, write_fd = os.pipe()
        self.reader = os.fdopen(read_fd, "r")
        self.writer = os.fdopen(write_fd, "w")
        self.addCleanup(self.reader.close)
        self.addCleanup(lambda: self.writer.closed or self.writer.close())

    def write(self, text):
        self.writer.write(text)
        self.writer.flush()

    def test_collects_lines_arriving_within_window(self):
        self.write("b\n")
        later = threading.Timer(0.03, self.write, ("c\n",))
        later.start()
        self.addCleanup(later.cancel)
        self.assertEqual(apply_tmux.drain_stdout(self.reader, "a\n", 0.3),
                         ["a\n", "b\n", "c\n"])

    def test_leaves_lines_after_window_unread(self):
        later = threading.Timer(0.3, self.write, ("b\n",))
        later.start()
        self.addCleanup(later.cancel)
        self.assertEqual(apply_tmux.drain_stdout(self.reader, "a\n", 0.05), ["a\n"])
        later.join()
        self.assertEqual(self.reader.readline(), "b\n")

    def test_returns_first_line_when_nothing_follows(self):
        start = time.monotonic()
        self.assertEqual(apply_tmux.drain_stdout(self.reader, "a\n", 0.1), ["a\n"])
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.09)
        self.assertLess(elapsed, 1)

    def test_stops_at_eof(self):
        self.write("b\n")
        self.writer.close()
        start = time.monotonic()
        self.assertEqual(apply_tmux.drain_stdout(self.reader, "a\n", 5), ["a\n", "b\n"])
        self.assertLess(time.monotonic() - start, 1)

    def test_zero_settle_does_not_read(self):
        self.write("b\n")
        self.assertEqual(apply_tmux.drain_stdout(self.reader, "a\n", 0), ["a\n"])
        self.assertEqual(self.reader.readline(), "b\n")


class MainLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="apply-tmux-test-")
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        tmux = bin_dir / "tmux"
        tmux.write_text(FAKE_TMUX)
        tmux.chmod(0o755)
        self.watcher = self.root / "agent_watcher.py"
        self.watcher.write_text(WATCHER)
        self.log = self.root / "tmux.log"
        self.socket = str(self.root / "sock")
        self.env = {
            **os.environ,
            "PATH": "%s%s%s" % (bin_dir, os.pathsep, os.environ.get("PATH", "")),
            "FAKE_TMUX_LOG": str(self.log),
            "FAKE_TMUX_QUOTA": "",
        }

    def run_adapter(self, **env):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/apply_tmux.py"),
             "--watcher", str(self.watcher), "--socket", self.socket],
            env={**self.env, **env}, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def calls(self):
        return self.log.read_text().splitlines()

    def watcher_argv(self):
        return json.loads(Path(str(self.watcher) + ".argv").read_text())

    def test_quota_defaults_on(self):
        self.run_adapter()
        self.assertEqual(self.watcher_argv(), ["--listen", self.socket + ".agent-watcher.sock"])

    def test_quota_off_passes_no_quota_before_listen(self):
        self.run_adapter(FAKE_TMUX_QUOTA="off")
        self.assertEqual(self.watcher_argv(),
                         ["--no-quota", "--listen", self.socket + ".agent-watcher.sock"])

    def test_bursts_coalesce_and_unchanged_writes_are_skipped(self):
        self.run_adapter()
        calls = self.calls()
        # Burst of three events -> one write; repeated identical state -> none;
        # new state -> one more.
        self.assertEqual(sum("refresh-client" in c for c in calls), 2, calls)
        writes = [c for c in calls if "@agent_state " in c]
        self.assertEqual(len(writes), 2, calls)
        self.assertIn("@agent_state thinking", writes[0])
        self.assertIn("@agent_state waiting-permission", writes[1])
        # The hello publishes the socket, which is cleared on exit.
        self.assertIn("-S %s set-option -g @agent_watcher_socket %s.agent-watcher.sock"
                      % (self.socket, self.socket), calls)
        self.assertEqual(calls[-1], "-S %s set-option -gu @agent_watcher_socket" % self.socket)

    def test_glyph_options_are_not_reread_per_write(self):
        self.run_adapter()
        style_reads = [c for c in self.calls() if "@agent-state-glyphs" in c]
        self.assertEqual(len(style_reads), 1)

    def test_exits_when_tmux_server_is_gone(self):
        result = self.run_adapter(FAKE_TMUX_DEAD="1")
        self.assertIn("tmux server gone", result.stderr)
        self.assertFalse(any("refresh-client" in c for c in self.calls()))


if __name__ == "__main__":
    unittest.main()
