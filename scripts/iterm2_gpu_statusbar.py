#!/usr/bin/env python3
"""iTerm2 AutoLaunch status bar component for cached GPU usage.

This script intentionally reads a tiny cache file only. It does not run ioreg,
powermetrics, or any other system probe from iTerm2's UI callback.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


DEFAULT_CACHE_PATH = Path("~/.cache/iterm2-gpu/gpu_usage.json").expanduser()
DEFAULT_STALE_AFTER_SECONDS = 18.0
DEFAULT_UPDATE_CADENCE_SECONDS = 2.5
IDENTIFIER = "dev.local.iterm2-gpu-status"
SPARKLINE_LEVELS = "▁▂▃▄▅▆▇"
SPARKLINE_SAMPLES = 24
FALLBACK_LINE = "▁▁▁▁"
PERCENT_GRAPH_GAP = "  "
GPU_ICON_1X_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAARCAYAAADUryzEAAAAmklEQVR4nL1TiwrAIAjM0Tf7"
    "Ef50w/DgCsfaGhMi7XGeXpXypalqe+K7HbtJJUNdNTOTDgADkG+oqrsAFjMb9nGnZqzmgx4H"
    "oMcD2/qmBE5QkTXmFmPuDe9zXLoKXp8Pas6QMYuxJkkJXGeWud2pIDiUqeE+q3AkPQII1Ohx"
    "XGq/PCRhJnhAXA6XAAYz/SV/VgcshvlqDbb9G0/cHW1jsKwIqAAAAABJRU5ErkJggg=="
)
GPU_ICON_2X_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAiCAYAAAA+stv/AAAAzklEQVR4nO2WAQrDMAhFVXZm"
    "D+GlUzb4I5MY7FiIo31QmmpSzDcmIboJUNX2fFbZgdBm5PIBMBSY5WkFZsYlUvBWwOMVQcSq"
    "CpNX7OU3s+l4j9BmHok+nJkR/J1C8E/XllAVBXRxFUQKChVaA+x8zb2HOU+Mj/xUQoGf7QNZ"
    "f10FNK6CqJ6zOR/+t0wVcOToFBnOJHs2wP7XZ0E7sw9Ep2GE0GYYjftGlKgC0GY5j6qjbBUw"
    "Gl3EIKXAt3YoJ1QdVf1Qx3+f7ecR2oxcPoAD5Nl/PfGbsFEAAAAASUVORK5CYII="
)


def cache_path_from_env() -> Path:
    raw = os.environ.get("ITERM2_GPU_CACHE_PATH")
    return Path(raw).expanduser() if raw else DEFAULT_CACHE_PATH


def read_payload(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.expanduser().read_text(encoding="utf-8").strip()
        if not raw:
            return None
        if raw.isdigit():
            return {"usage_percent": int(raw), "timestamp": time.time()}
        return json.loads(raw)
    except Exception:
        return None


def usage_from_payload(payload: dict[str, Any] | None, now: float | None = None) -> int | None:
    if not isinstance(payload, dict):
        return None

    value = payload.get("usage_percent")
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        return None
    if value < 0 or value > 100:
        return None

    timestamp = payload.get("timestamp")
    stale_after = payload.get("stale_after_seconds", DEFAULT_STALE_AFTER_SECONDS)
    if isinstance(timestamp, (int, float)) and isinstance(stale_after, (int, float)):
        if (now or time.time()) - float(timestamp) > float(stale_after):
            return None

    return value


def history_from_payload(payload: dict[str, Any] | None) -> list[int]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("history_percent", [])
    if not isinstance(raw, list):
        return []

    history: list[int] = []
    for item in raw[-SPARKLINE_SAMPLES:]:
        if isinstance(item, bool):
            continue
        if isinstance(item, float) and item.is_integer():
            item = int(item)
        if isinstance(item, int) and 0 <= item <= 100:
            history.append(item)
    return history


def sparkline_from_history(history: list[int]) -> str:
    if not history:
        return ""
    if len(history) < SPARKLINE_SAMPLES:
        history = [history[0]] * (SPARKLINE_SAMPLES - len(history)) + history
    else:
        history = history[-SPARKLINE_SAMPLES:]
    max_index = len(SPARKLINE_LEVELS) - 1
    return "".join(SPARKLINE_LEVELS[round((value / 100) * max_index)] for value in history)


def render_gpu_variants(path: Path | None = None, show_sparkline: bool = True) -> list[str]:
    payload = read_payload(path or cache_path_from_env())
    usage = usage_from_payload(payload)
    percent = f"{usage}%" if usage is not None else "--%"
    aligned_percent = f"{usage:>3}%" if usage is not None else "--%"

    variants = [percent.strip()]
    if show_sparkline:
        sparkline = sparkline_from_history(history_from_payload(payload))
        if sparkline:
            variants = [
                f"{aligned_percent}{PERCENT_GRAPH_GAP}{sparkline[-24:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-16:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-14:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-13:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-12:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-8:]}",
                f"{percent}{PERCENT_GRAPH_GAP}{sparkline[-4:]}",
                percent,
            ]
        elif usage is None:
            variants.insert(0, f"{percent}{PERCENT_GRAPH_GAP}{FALLBACK_LINE}")
    return variants


def render_gpu_text(path: Path | None = None, show_sparkline: bool = True) -> str:
    return render_gpu_variants(path, show_sparkline)[0]


async def register_component(connection: Any) -> None:
    import iterm2

    component = iterm2.StatusBarComponent(
        short_description="GPU",
        detailed_description="Shows cached macOS GPU utilization",
        knobs=[
            iterm2.CheckboxKnob(
                "Show sparkline",
                True,
                "show_sparkline_v2",
            )
        ],
        exemplar="56% ▁▂▃▄▃▂ GPU",
        update_cadence=DEFAULT_UPDATE_CADENCE_SECONDS,
        identifier=IDENTIFIER,
        icons=[
            iterm2.StatusBarComponent.Icon(1, GPU_ICON_1X_BASE64),
            iterm2.StatusBarComponent.Icon(2, GPU_ICON_2X_BASE64),
        ],
    )

    @iterm2.StatusBarRPC
    async def gpu_status(knobs):
        show_sparkline = bool(knobs.get("show_sparkline_v2", True))
        return render_gpu_variants(show_sparkline=show_sparkline)

    await component.async_register(connection, gpu_status, timeout=0.5)


def dry_run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run the iTerm2 GPU status text renderer.")
    parser.add_argument("--cache-path", type=Path, default=cache_path_from_env())
    parser.add_argument("--hide-sparkline", action="store_true")
    args = parser.parse_args(argv)
    for variant in render_gpu_variants(args.cache_path, not args.hide_sparkline):
        print(variant, flush=True)
    return 0


def main() -> None:
    import sys

    if "--dry-run" in sys.argv:
        filtered = [arg for arg in sys.argv[1:] if arg != "--dry-run"]
        raise SystemExit(dry_run(filtered))

    try:
        import iterm2
    except ImportError as exc:
        raise SystemExit(
            "This script must run inside iTerm2's Python environment, "
            "or use --dry-run for local validation."
        ) from exc

    iterm2.run_forever(register_component)


if __name__ == "__main__":
    main()
