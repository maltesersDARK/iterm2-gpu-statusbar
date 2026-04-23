#!/usr/bin/env python3
"""Low-overhead macOS GPU usage collector for an iTerm2 status component.

The collector samples IORegistry GPU performance counters and writes a tiny
JSON cache. The iTerm2 UI script reads only that cache, so terminal rendering
does not run system probes directly.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


DEFAULT_CACHE_PATH = Path("~/.cache/iterm2-gpu/gpu_usage.json").expanduser()
DEFAULT_INTERVAL_SECONDS = 2.5
DEFAULT_STALE_AFTER_SECONDS = 18.0
IOREG_TIMEOUT_SECONDS = 1.5
HISTORY_LENGTH = 24
EMA_ALPHA = 0.36
HYSTERESIS_PERCENT = 2

USAGE_KEYS = (
    "Device Utilization %",
    "GPU Activity(%)",
    "GPU Activity %",
    "Renderer Utilization %",
    "Tiler Utilization %",
)


class CollectorStopped(Exception):
    """Raised when the process receives a stop signal."""


def _stop_handler(signum: int, _frame: Any) -> None:
    raise CollectorStopped(f"received signal {signum}")


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def cache_path_from_env() -> Path:
    raw = os.environ.get("ITERM2_GPU_CACHE_PATH")
    return Path(raw).expanduser() if raw else DEFAULT_CACHE_PATH


def run_ioreg() -> bytes:
    """Return XML plist bytes from the Apple Silicon GPU accelerator node."""

    command = ["/usr/sbin/ioreg", "-r", "-c", "AGXAccelerator", "-d", "1", "-a"]
    return subprocess.check_output(
        command,
        stderr=subprocess.DEVNULL,
        timeout=IOREG_TIMEOUT_SECONDS,
    )


def iter_dicts(value: Any) -> Any:
    """Yield nested dictionaries from plist-like data."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def numeric_percent(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(100.0, float(value)))
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        try:
            return max(0.0, min(100.0, float(stripped)))
        except ValueError:
            return None
    return None


def extract_usage(plist_data: bytes) -> dict[str, Any]:
    """Extract a best-effort GPU utilization percentage from IORegistry plist."""

    root = plistlib.loads(plist_data)
    samples: list[dict[str, Any]] = []

    for item in iter_dicts(root):
        stats = item.get("PerformanceStatistics")
        if not isinstance(stats, dict):
            continue

        values: dict[str, float] = {}
        for key in USAGE_KEYS:
            percent = numeric_percent(stats.get(key))
            if percent is not None:
                values[key] = percent

        if values:
            usage = values.get("Device Utilization %", max(values.values()))
            samples.append(
                {
                    "usage_percent": int(round(usage)),
                    "raw": values,
                    "model": item.get("model") or item.get("IORegistryEntryName"),
                }
            )

    if not samples:
        raise RuntimeError("no GPU PerformanceStatistics utilization keys found")

    # Prefer the busiest accelerator when multiple entries exist.
    return max(samples, key=lambda sample: sample["usage_percent"])


def collect_once() -> dict[str, Any]:
    sample = extract_usage(run_ioreg())
    return {
        "schema_version": 1,
        "metric": "gpu",
        "source": "ioreg.AGXAccelerator.PerformanceStatistics",
        "raw_usage_percent": sample["usage_percent"],
        "timestamp": time.time(),
        "stale_after_seconds": DEFAULT_STALE_AFTER_SECONDS,
        "raw": sample["raw"],
        "model": sample.get("model"),
        "status": "ok",
    }


def read_previous_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_history(path: Path) -> list[int]:
    payload = read_previous_payload(path)
    raw = payload.get("history_percent", [])
    if not isinstance(raw, list):
        return []

    history: list[int] = []
    for item in raw[-HISTORY_LENGTH:]:
        if isinstance(item, bool):
            continue
        if isinstance(item, float) and item.is_integer():
            item = int(item)
        if isinstance(item, int) and 0 <= item <= 100:
            history.append(item)
    return history


def unavailable_payload(reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "metric": "gpu",
        "source": "ioreg.AGXAccelerator.PerformanceStatistics",
        "raw_usage_percent": None,
        "usage_percent": None,
        "timestamp": time.time(),
        "stale_after_seconds": DEFAULT_STALE_AFTER_SECONDS,
        "status": "unavailable",
        "error": reason[:240],
    }


def is_previous_payload_fresh(payload: dict[str, Any], now: float) -> bool:
    timestamp = payload.get("timestamp")
    stale_after = payload.get("stale_after_seconds", DEFAULT_STALE_AFTER_SECONDS)
    if not isinstance(timestamp, (int, float)) or not isinstance(stale_after, (int, float)):
        return False
    return now - float(timestamp) <= float(stale_after)


def previous_number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def smooth_payload(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    now = float(payload.get("timestamp", time.time()))
    previous = read_previous_payload(path)
    history = read_history(path)

    raw_value = previous_number(payload, "raw_usage_percent")
    previous_display = previous_number(previous, "usage_percent")
    previous_ema = previous_number(previous, "ema_usage_percent")

    if raw_value is None:
        if previous_display is not None and is_previous_payload_fresh(previous, now):
            payload["usage_percent"] = int(round(previous_display))
            payload["ema_usage_percent"] = previous_ema if previous_ema is not None else previous_display
            payload["status"] = "stale_probe_reused"
            payload["history_percent"] = history[-HISTORY_LENGTH:]
        else:
            payload["history_percent"] = history[-4:]
        return payload

    ema = raw_value if previous_ema is None else (EMA_ALPHA * raw_value) + ((1 - EMA_ALPHA) * previous_ema)
    rounded_ema = int(round(max(0.0, min(100.0, ema))))

    if previous_display is not None and abs(rounded_ema - previous_display) < HYSTERESIS_PERCENT:
        display = int(round(previous_display))
    else:
        display = rounded_ema

    payload["usage_percent"] = display
    payload["ema_usage_percent"] = round(ema, 3)
    if not history or history[-1] != display:
        history = [*history, display][-HISTORY_LENGTH:]
    payload["history_percent"] = history[-HISTORY_LENGTH:]
    return payload


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(data)
        handle.write("\n")
        temp_name = handle.name

    os.replace(temp_name, path)


def format_text(payload: dict[str, Any]) -> str:
    value = payload.get("usage_percent")
    return f"{value}%" if isinstance(value, int) else "--%"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect macOS GPU usage for iTerm2.")
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=cache_path_from_env(),
        help="JSON cache path. Default: %(default)s",
    )
    parser.add_argument(
        "--interval",
        type=positive_float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Polling interval in seconds. Default: %(default)s",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect one sample, write the cache, and exit.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_value",
        help="Print the compact status text after each sample.",
    )
    parser.add_argument(
        "--allow-unavailable-write",
        action="store_true",
        help="Write --%% fallback payload when sampling fails.",
    )
    return parser


def sample_and_write(args: argparse.Namespace) -> int:
    try:
        payload = collect_once()
        exit_code = 0
    except Exception as exc:
        payload = unavailable_payload(str(exc))
        exit_code = 2
        if not args.allow_unavailable_write:
            raise

    cache_path = args.cache_path.expanduser()
    payload = smooth_payload(cache_path, payload)
    write_cache(cache_path, payload)
    if args.print_value:
        print(format_text(payload), flush=True)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.cache_path = args.cache_path.expanduser()

    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)

    if args.once:
        return sample_and_write(args)

    while True:
        try:
            sample_and_write(args)
        except CollectorStopped:
            return 0
        except Exception:
            if args.print_value:
                print("--%", flush=True)
        try:
            time.sleep(args.interval)
        except CollectorStopped:
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CollectorStopped:
        raise SystemExit(0)
