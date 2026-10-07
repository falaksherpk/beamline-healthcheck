"""Checks disk, memory, load and optional TCP targets; exit 0 if all pass, 1 if any fails."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from beamline_healthcheck import __version__

METRIC_PREFIX = "beamline_healthcheck"


@dataclass(frozen=True)
class Result:
    check: str  # e.g. "disk", "memory", "load", "tcp"
    target: str  # what was checked: a path, a host:port, or "" for host-wide checks
    ok: bool
    value: float  # the measured number (ratio, per-CPU load, or connect seconds)
    detail: str  # one human-readable line


def check_disk(path: str, min_free_ratio: float) -> Result:
    usage = shutil.disk_usage(path)
    free = usage.free / usage.total
    ok = free >= min_free_ratio
    return Result(
        "disk", path, ok, free, f"disk {path}: {free:.1%} free (min {min_free_ratio:.0%})"
    )


def read_meminfo(path: str = "/proc/meminfo") -> dict[str, int]:
    """Return /proc/meminfo as {field: kB}."""
    fields: dict[str, int] = {}
    for line in Path(path).read_text().splitlines():
        name, _, rest = line.partition(":")
        fields[name] = int(rest.split()[0])
    return fields


def check_memory(min_available_ratio: float, meminfo: str = "/proc/meminfo") -> Result:
    # MemAvailable, not MemFree: page cache is reclaimable and counted as available.
    info = read_meminfo(meminfo)
    available = info["MemAvailable"] / info["MemTotal"]
    ok = available >= min_available_ratio
    return Result(
        "memory",
        "",
        ok,
        available,
        f"memory: {available:.1%} available (min {min_available_ratio:.0%})",
    )


def check_load(max_per_cpu: float) -> Result:
    cpus = len(os.sched_getaffinity(0))
    per_cpu = os.getloadavg()[0] / cpus
    ok = per_cpu <= max_per_cpu
    return Result(
        "load",
        "",
        ok,
        per_cpu,
        f"load: 1-min {per_cpu:.2f} per CPU on {cpus} CPU(s) (max {max_per_cpu:.2f})",
    )


def check_tcp(target: str, timeout: float) -> Result:
    # A plain TCP connect needs no privileges (unlike ICMP ping), so it behaves the
    # same on a host, in a rootless container and in an unprivileged Apptainer image.
    host, _, port = target.rpartition(":")
    start = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
    except OSError as exc:
        return Result("tcp", target, False, 0.0, f"tcp {target}: unreachable ({exc})")
    elapsed = time.monotonic() - start
    return Result(
        "tcp", target, True, elapsed, f"tcp {target}: connected in {elapsed * 1000:.0f} ms"
    )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(r: Result) -> str:
    return f'{{check="{r.check}",target="{_escape(r.target)}"}}'


def render_prometheus(results: Sequence[Result], now: float) -> str:
    """Render results in the Prometheus text exposition format (node_exporter textfile)."""
    lines = [
        f"# HELP {METRIC_PREFIX}_check_ok 1 if the check passed, 0 if it failed.",
        f"# TYPE {METRIC_PREFIX}_check_ok gauge",
    ]
    for r in results:
        lines.append(f"{METRIC_PREFIX}_check_ok{_labels(r)} {int(r.ok)}")
    lines += [
        f"# HELP {METRIC_PREFIX}_check_value Measured value: free/available ratio, "
        "1-min load per CPU, or TCP connect seconds.",
        f"# TYPE {METRIC_PREFIX}_check_value gauge",
    ]
    for r in results:
        lines.append(f"{METRIC_PREFIX}_check_value{_labels(r)} {r.value:g}")
    lines += [
        f"# HELP {METRIC_PREFIX}_last_run_timestamp_seconds Unix time of the last run.",
        f"# TYPE {METRIC_PREFIX}_last_run_timestamp_seconds gauge",
        f"{METRIC_PREFIX}_last_run_timestamp_seconds {now:.3f}",
    ]
    return "\n".join(lines) + "\n"


def write_atomically(path: Path, text: str) -> None:
    # Write to a temp file in the same directory, then rename over the target: a
    # reader (node_exporter's textfile collector) sees the old file or the new one,
    # never a half-written one. Same directory = same filesystem = atomic rename.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _tcp_target(value: str) -> str:
    host, sep, port = value.rpartition(":")
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise argparse.ArgumentTypeError(f"expected HOST:PORT, got {value!r}")
    return value


def _ratio(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError(f"expected a ratio between 0 and 1, got {value}")
    return number


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="beamline-healthcheck",
        description="Check disk, memory, load and optional TCP targets. "
        "Exit 0 if every check passes, 1 if any fails, 2 on usage errors.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--disk-path",
        action="append",
        metavar="PATH",
        help="filesystem to check (repeatable; default: /)",
    )
    p.add_argument(
        "--min-disk-free",
        type=_ratio,
        default=0.10,
        metavar="RATIO",
        help="minimum free ratio per filesystem (default: 0.10)",
    )
    p.add_argument(
        "--min-mem-available",
        type=_ratio,
        default=0.10,
        metavar="RATIO",
        help="minimum MemAvailable/MemTotal (default: 0.10)",
    )
    p.add_argument(
        "--max-load-per-cpu",
        type=float,
        default=2.0,
        metavar="N",
        help="maximum 1-minute load average per CPU (default: 2.0)",
    )
    p.add_argument(
        "--tcp",
        action="append",
        type=_tcp_target,
        default=[],
        metavar="HOST:PORT",
        help="TCP target that must accept a connection (repeatable)",
    )
    p.add_argument(
        "--tcp-timeout",
        type=float,
        default=3.0,
        metavar="SECONDS",
        help="connect timeout per TCP target (default: 3)",
    )
    p.add_argument(
        "--prometheus",
        type=Path,
        metavar="FILE",
        help="also write metrics to FILE, atomically (node_exporter textfile collector)",
    )
    p.add_argument("-q", "--quiet", action="store_true", help="print failures only")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = [check_disk(path, args.min_disk_free) for path in (args.disk_path or ["/"])]
    results.append(check_memory(args.min_mem_available))
    results.append(check_load(args.max_load_per_cpu))
    results += [check_tcp(target, args.tcp_timeout) for target in args.tcp]

    for r in results:
        if r.ok and args.quiet:
            continue
        print(f"[{'OK' if r.ok else 'FAIL'}] {r.detail}")

    if args.prometheus is not None:
        write_atomically(args.prometheus, render_prometheus(results, time.time()))

    return 0 if all(r.ok for r in results) else 1
