# iTerm2 GPU Status Bar Design

## Goal

Provide a macOS iTerm2 Python API custom status bar component that can sit next to native CPU, memory, and battery components without looking like a dashboard widget. The UI is intentionally plain text next to a static icon:

```text
42% ▁▂▃▄▅▄▃▂▃▄▅▆▅▄
```

When data is unavailable, stale, or malformed, it renders:

```text
--% ▁▁▁▁
```

## Architecture

The implementation is split into two processes:

- `scripts/gpu_collector.py`
  - Samples GPU usage.
  - Writes a tiny JSON cache file.
  - Runs outside iTerm2, normally under a user `launchd` agent.
- `scripts/iterm2_gpu_statusbar.py`
  - Registers an iTerm2 Python API `StatusBarComponent`.
  - Reads only the cache file.
  - Never runs `ioreg`, `powermetrics`, or shell commands from the status bar callback.

This separation keeps iTerm2 responsive even if GPU sampling fails or becomes slow.

## Data Source Comparison

| Source | Accuracy | Latency | CPU overhead | Battery impact | Complexity | Stability | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ioreg -r -c AGXAccelerator -d 1 -a` | Good practical utilization via `PerformanceStatistics` | Immediate snapshot | Low for a 3s background collector | Acceptable | Low | Keys may drift across macOS, but failure is detectable | Default |
| `powermetrics --samplers gpu_power` | Strong for power, residency, frequency, and future ANE | Sample-window based | Higher | Higher for always-on status use | Medium | Official tool, but requires superuser here | Diagnostics/future backend |
| Private IOReport bindings | Potentially closest to system tools | Good | Potentially low | Potentially low | High | Private API risk | Not used |
| `system_profiler` | Poor for live usage | Slow | High | Poor | Low | Stable but wrong tool | Not used |

Local observations on this Mac:

- `ioreg -r -c AGXAccelerator -d 1 -a` returned `PerformanceStatistics` with `Device Utilization %`, `Renderer Utilization %`, and `Tiler Utilization %`.
- One local raw `ioreg` sample took roughly `0.024s` wall time and produced about `99 KB` of plist output.
- One local Python collector one-shot took roughly `0.09s` real time including Python startup, plist parsing, and atomic cache write.
- `powermetrics --samplers gpu_power -n 1 -i 1000` returned `powermetrics must be invoked as the superuser`.

## Chosen Method

The default collector uses `ioreg` because it is non-root, available on macOS, fast enough at a 2.5 second cadence, and exposes the utilization percentage needed for the status bar.

The collector parses plist output with Python `plistlib`, searches nested `PerformanceStatistics`, and prefers `Device Utilization %`. If that key is missing, it uses the busiest available utilization among renderer, tiler, or GPU activity keys.

## Cadence

Default collector cadence is 2.5 seconds. UI update cadence is also 2.5 seconds so repaint timing follows the cache without redundant redraws.

Reasoning:

- GPU usage in the iTerm2 status bar is an ambient signal, not an animation or profiler.
- 2.5 seconds is a compromise between lower wakeups and a graph that feels slightly more responsive.
- It still feels current beside native CPU/RAM/Battery components.
- The cache is treated as stale after 18 seconds, so brief probe failures do not immediately flash `--%`.
- EMA smoothing with alpha `0.36` and 2 percentage-point hysteresis reduces flicker and tiny redraws while making the graph react a little faster.

## Visual Fit

The component intentionally uses:

- plain text format
- a minimal static icon through the iTerm2 status bar icon API
- no HTML
- no popover
- no color overrides
- short description `GPU`
- exemplar `56% ▁▂▃▄▅▄▃▂▃▄`

iTerm2 native CPU/RAM/Battery components can render internal graphs that Python API components cannot reproduce exactly. The matching strategy here is restraint: compact text, native default font/color/background, and the same status bar layout controls as other components.

The component returns variable-length strings so iTerm2 can choose the longest fitting value:

- default: ` 56%  ▁▂▃▄▅▄▃▂▃▄▅▆▅▄▃▂▃▄▅▄▃▂▃▄`, `56%  ▃▄▅▄▃▂▃▄▅▄▃▂▃▄▅▄`, `56%  ▅▄▃▂▃▄▅▄▃▂▃▄▅▄`, `56%  ▄▃▂▃▄▅▄▃▂▃▄▅▄`, `56%  ▃▂▃▄▅▄▃▂▃▄▅▄`, `56%`
- fallback: `--% ▁▁▁▁`, `--%`

The text label `GPU` is intentionally removed from the rendered value. The icon already identifies the metric; keeping a second text label wastes width and makes the component read like a custom badge. Percent-first text followed by a long sparkline better resembles the native CPU/Memory pattern: number on the left, graph-like signal extending to the right.

## Smoothing

The collector stores raw and display-oriented fields:

- `raw_usage_percent`: immediate IORegistry value.
- `ema_usage_percent`: exponentially smoothed value.
- `usage_percent`: displayed value after hysteresis.
- `history_percent`: recent displayed values for the sparkline.

Raw GPU utilization can bounce by small amounts every sample. Without smoothing, the percent and graph redraw too often and make the component feel busier than native iTerm2 widgets. EMA alpha `0.36` keeps meaningful movement while damping one-sample spikes. Hysteresis holds the previous display value when the rounded smoothed value changes by less than 2 percentage points, reducing flicker and width churn.

The long variant right-aligns the percent in a fixed four-character column, so `8%`, `10%`, and `100%` keep the sparkline starting at the same visual column as much as the status bar font allows.

The shorter variants deliberately keep 16-block, 14-block, 13-block, 12-block, 8-block, and 4-block sparklines before falling back to percent-only. This prevents narrow iTerm2 status bar configurations from hiding the graph entirely. The percent and graph use a two-space gap so the value does not visually collide with the sparkline.

The sparkline history only advances when the displayed percentage changes. This avoids the text-only graph shifting left on every probe while the value is effectively stable, which was the main source of the visible flicker in the prototype.

## Extension Point

Future ANE usage should be added as another metric backend rather than mixed into the iTerm2 UI script.

Suggested path:

- Add a backend function in `scripts/gpu_collector.py` or split `scripts/metrics_collector.py`.
- Write payloads with `"metric": "ane"` and a stable schema.
- Add a separate iTerm2 component script or a knob that selects `gpu` vs `ane`.
- Consider `powermetrics --samplers ane_power` only if the user accepts sudo/root or a privileged helper.
