import importlib.util
import os
from pathlib import Path
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("apply_tmux", ROOT / "scripts/apply_tmux.py")
apply_tmux = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply_tmux)


class DrainTests(unittest.TestCase):
    def setUp(self):
        self.read_fd, self.write_fd = os.pipe()
        self.reader = apply_tmux.LineReader(self.read_fd)

    def tearDown(self):
        os.close(self.read_fd)
        if self.write_fd is not None:
            os.close(self.write_fd)

    def test_burst_in_one_write_is_coalesced_without_waiting(self):
        os.write(self.write_fd, b"1\n2\n3\n")
        first = self.reader.readline()
        lines = apply_tmux.drain_stdout(self.reader, first, 0.1)
        self.assertEqual(lines, ["1\n", "2\n", "3\n"])

    def test_buffered_lines_skip_the_settle_wait(self):
        os.write(self.write_fd, b"1\n2\n")
        self.reader.readline()
        started = time.monotonic()
        self.assertEqual(self.reader.readline(5.0), "2\n")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_partial_line_waits_for_newline_and_eof_flushes(self):
        os.write(self.write_fd, b'{"a": 1')
        self.assertIsNone(self.reader.readline(0.05))
        os.write(self.write_fd, b"}\ntail")
        self.assertEqual(self.reader.readline(), '{"a": 1}\n')
        os.close(self.write_fd)
        self.write_fd = None
        self.assertEqual(self.reader.readline(), "tail")
        self.assertEqual(self.reader.readline(), "")


if __name__ == "__main__":
    unittest.main()
