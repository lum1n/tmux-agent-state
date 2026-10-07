import importlib.util
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("manage_watcher", ROOT / "scripts/manage_watcher.py")
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)

ADAPTER = """\
import signal
from pathlib import Path
import os
import subprocess
import sys
import time

watcher = sys.argv[sys.argv.index("--watcher") + 1]
socket = sys.argv[sys.argv.index("--socket") + 1]
with Path(socket + ".starts").open("a") as started:
    started.write(str(os.getpid()) + "\\n")
proc = subprocess.Popen([sys.executable, "-u", watcher, "--listen", socket + ".agent-watcher.sock"])
signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
try:
    while True:
        time.sleep(0.05)
finally:
    proc.terminate()
    proc.wait(timeout=2)
"""

WATCHER = """\
from pathlib import Path
import os
import sys
import time

Path(sys.argv[0] + ".pid").write_text(str(os.getpid()))
while True:
    time.sleep(0.05)
"""


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="watcher-test-", dir=ROOT)
        self.root = Path(self.temp.name)
        self.scripts = self.root / "plugin with spaces" / "scripts"
        self.scripts.mkdir(parents=True)
        (self.scripts / "utils").mkdir()
        shutil.copyfile(ROOT / "scripts/manage_watcher.py", self.scripts / "manage_watcher.py")
        (self.scripts / "apply_tmux.py").write_text(ADAPTER)
        (self.scripts / "run-watcher.sh").write_text("")
        (self.scripts / "utils/tmux.sh").write_text("")
        self.watcher = self.root / "classifier" / "agent_watcher.py"
        self.watcher.parent.mkdir()
        self.watcher.write_text(WATCHER)
        self.socket = str(self.root / "tmux socket")
        self.pidfile = Path(self.socket + ".agent-state.pid")
        self.statefile = Path(self.socket + ".agent-state.state")
        self.processes = {}
        self.foreign = None

    def tearDown(self):
        if self.pidfile.exists():
            pid = int(self.pidfile.read_text())
            identity = manager.process_identity(pid)
            if identity and "/apply_tmux.py --watcher " in identity:
                self.processes[pid] = identity
        for pid, identity in self.processes.items():
            if manager.process_identity(pid) == identity:
                manager.stop_daemon(pid, identity, self.socket)
        if self.foreign:
            self.foreign.terminate()
            self.foreign.wait(timeout=3)
        self.temp.cleanup()

    def command(self, *extra):
        return [sys.executable, str(self.scripts / "manage_watcher.py"),
                "--watcher", str(self.watcher), "--socket", self.socket, *extra]

    def run_manager(self, *extra):
        subprocess.run(self.command(*extra), capture_output=True, text=True, check=True)
        pid = int(self.pidfile.read_text())
        self.processes[pid] = manager.process_identity(pid)
        deadline = time.monotonic() + 3
        childfile = Path(str(self.watcher) + ".pid")
        while time.monotonic() < deadline:
            if childfile.exists():
                child = int(childfile.read_text())
                identity = manager.process_identity(child)
                if identity and str(self.watcher) in identity:
                    return pid, child
            time.sleep(0.02)
        self.fail("classifier did not become responsive")

    def assert_stopped(self, pid, child):
        self.assertIsNone(manager.process_identity(pid))
        self.assertIsNone(manager.process_identity(child))

    def test_unchanged_code_keeps_daemon(self):
        first = self.run_manager()
        self.assertEqual(first, self.run_manager())

    def test_classifier_module_change_restarts_daemon(self):
        pid, child = self.run_manager()
        module = self.watcher.parent / "harnesses/copilot.py"
        module.parent.mkdir()
        module.write_text("VERSION = 1\n")
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_adapter_change_restarts_daemon(self):
        pid, child = self.run_manager()
        adapter = self.scripts / "apply_tmux.py"
        adapter.write_text(ADAPTER + "\n# updated\n")
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_quota_option_change_restarts_daemon(self):
        pid, child = self.run_manager()
        self.assertEqual((pid, child), self.run_manager("--quota", "on"))
        updated, _ = self.run_manager("--quota", "off")
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)
        self.assertEqual(updated, self.run_manager("--quota", "off")[0])

    def test_watcher_path_change_restarts_daemon(self):
        pid, child = self.run_manager()
        self.watcher = self.watcher.parent / "custom-watcher"
        self.watcher.write_text(WATCHER)
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_legacy_daemon_without_metadata_restarts(self):
        adapter = self.scripts / "apply_tmux.py"
        adapter.write_text(ADAPTER.replace(
            "signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))", "",
        ))
        pid, child = self.run_manager()
        self.statefile.unlink()
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_dead_daemon_is_replaced(self):
        pid, child = self.run_manager()
        manager.stop_daemon(pid, self.processes[pid], self.socket)
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_foreign_pid_is_never_signalled(self):
        self.foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.pidfile.write_text(str(self.foreign.pid))
        pid, _ = self.run_manager()
        self.assertNotEqual(pid, self.foreign.pid)
        self.assertIsNone(self.foreign.poll())

    def test_concurrent_checks_start_only_one_daemon(self):
        callers = [subprocess.Popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                   for _ in range(8)]
        for caller in callers:
            _, error = caller.communicate(timeout=10)
            self.assertEqual(caller.returncode, 0, error.decode())
        pid, _ = self.run_manager()
        log = Path(self.socket + ".agent-state.log").read_text()
        self.assertNotIn("restarting", log)
        self.assertEqual(json.loads(self.statefile.read_text())["identity"],
                         manager.process_identity(pid))
        self.assertEqual(log, "")
        self.assertEqual(Path(self.socket + ".starts").read_text().splitlines(), [str(pid)])

    def test_corrupt_metadata_restarts_daemon(self):
        pid, child = self.run_manager()
        self.statefile.write_text("{broken")
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_content_fingerprint_ignores_documentation(self):
        before = manager.fingerprint(self.watcher, self.scripts)
        (self.watcher.parent / "README.md").write_text("Documentation update")
        self.assertEqual(before, manager.fingerprint(self.watcher, self.scripts))
        self.watcher.write_text(WATCHER + "\n# changed\n")
        self.assertNotEqual(before, manager.fingerprint(self.watcher, self.scripts))

    def test_held_lock_does_not_start_daemon(self):
        with Path(self.socket + ".agent-state.start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            subprocess.run(self.command(), capture_output=True, check=True)
            self.assertFalse(self.pidfile.exists())
        self.run_manager()

    def test_forced_shutdown_still_stops_classifier(self):
        self.watcher.write_text(WATCHER.replace(
            "while True:", "import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nwhile True:",
        ))
        pid, child = self.run_manager()
        self.statefile.unlink()
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)

    def test_real_adapter_cleans_up_classifier_on_restart(self):
        wrapper = f"""\
import sys
from pathlib import Path
sys.path.insert(0, {str(ROOT / "scripts")!r})
import apply_tmux
class FakeTmux:
    def __init__(self, socket):
        self.socket = socket
    def alive(self):
        return True
    def show_global(self, option, default=""):
        return default
    def run(self, batches):
        Path(self.socket + ".options").write_text(repr(batches))
    def refresh(self):
        pass
apply_tmux.Tmux = FakeTmux
raise SystemExit(apply_tmux.main())
"""
        (self.scripts / "apply_tmux.py").write_text(wrapper)
        self.watcher.write_text(WATCHER.replace(
            "while True:",
            'print(\'{"type":"hello"}\', flush=True)\nwhile True:',
        ))
        pid, child = self.run_manager()
        deadline = time.monotonic() + 3
        options = Path(self.socket + ".options")
        while not options.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(options.exists(), "adapter did not publish watcher socket")
        self.statefile.unlink()
        updated, _ = self.run_manager()
        self.assertNotEqual(pid, updated)
        self.assert_stopped(pid, child)


if __name__ == "__main__":
    unittest.main()
