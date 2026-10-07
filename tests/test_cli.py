"""Unit tests (stdlib unittest, so every build tool can run them without extra dependencies)."""

import io
import socket
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from beamline_healthcheck import cli


class MemoryTests(unittest.TestCase):
    def test_uses_memavailable_not_memfree(self):
        with tempfile.TemporaryDirectory() as d:
            meminfo = Path(d, "meminfo")
            meminfo.write_text("MemTotal: 1000 kB\nMemFree: 50 kB\nMemAvailable: 600 kB\n")
            result = cli.check_memory(0.10, meminfo=str(meminfo))
        self.assertTrue(result.ok)
        self.assertAlmostEqual(result.value, 0.6)

    def test_fails_below_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            meminfo = Path(d, "meminfo")
            meminfo.write_text("MemTotal: 1000 kB\nMemAvailable: 50 kB\n")
            self.assertFalse(cli.check_memory(0.10, meminfo=str(meminfo)).ok)


class DiskTests(unittest.TestCase):
    def test_impossible_threshold_fails(self):
        self.assertFalse(cli.check_disk("/", 1.0).ok)

    def test_zero_threshold_passes(self):
        self.assertTrue(cli.check_disk("/", 0.0).ok)


class TcpTests(unittest.TestCase):
    def test_listening_socket_passes(self):
        with socket.create_server(("127.0.0.1", 0)) as server:
            port = server.getsockname()[1]
            self.assertTrue(cli.check_tcp(f"127.0.0.1:{port}", 2.0).ok)

    def test_closed_port_fails(self):
        with socket.create_server(("127.0.0.1", 0)) as server:
            port = server.getsockname()[1]
        # the socket is closed now, so nothing listens on that port
        self.assertFalse(cli.check_tcp(f"127.0.0.1:{port}", 2.0).ok)

    def test_bad_target_is_a_usage_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            cli.main(["--tcp", "no-port-here"])
        self.assertEqual(ctx.exception.code, 2)


class PrometheusTests(unittest.TestCase):
    def test_render_and_atomic_write(self):
        results = [
            cli.Result("disk", "/", True, 0.5, ""),
            cli.Result("tcp", 'odd"name:1', False, 0.0, ""),
        ]
        text = cli.render_prometheus(results, now=1700000000.0)
        self.assertIn('beamline_healthcheck_check_ok{check="disk",target="/"} 1', text)
        self.assertIn('target="odd\\"name:1"} 0', text)
        self.assertTrue(text.endswith("\n"))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d, "healthcheck.prom")
            cli.write_atomically(out, text)
            self.assertEqual(out.read_text(), text)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["healthcheck.prom"])


class ExitCodeTests(unittest.TestCase):
    def test_all_pass_exits_0(self):
        with redirect_stdout(io.StringIO()):
            rc = cli.main(
                ["--min-disk-free", "0", "--min-mem-available", "0", "--max-load-per-cpu", "1000"]
            )
        self.assertEqual(rc, 0)

    def test_any_fail_exits_1(self):
        with redirect_stdout(io.StringIO()):
            rc = cli.main(
                ["--min-disk-free", "1", "--min-mem-available", "0", "--max-load-per-cpu", "1000"]
            )
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
