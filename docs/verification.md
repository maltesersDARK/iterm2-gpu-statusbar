# Dry-Run Verification

These checks do not write to:

- `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`
- `~/Library/LaunchAgents/`
- `~/.cache/iterm2-gpu/`

Use a repo-local temp path instead.

## Syntax Checks

```sh
python3 -m py_compile scripts/gpu_collector.py scripts/iterm2_gpu_statusbar.py
plutil -lint templates/dev.local.iterm2-gpu-collector.plist
file assets/gpu-chip.png assets/gpu-chip@2x.png
```

## Collector One-Shot Test

```sh
mkdir -p tmp
python3 scripts/gpu_collector.py \
  --once \
  --print \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

Expected output:

```text
42%
```

The number will vary. If the GPU counter is unavailable and you want to test fallback cache writing:

```sh
python3 scripts/gpu_collector.py \
  --once \
  --print \
  --allow-unavailable-write \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

## Status Renderer Dry Run

```sh
python3 scripts/iterm2_gpu_statusbar.py \
  --dry-run \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

Expected output:

```text
 42%  ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
42%  ▁▁▁▁
42%
```

To inspect variable-length sparkline variants:

```sh
python3 scripts/iterm2_gpu_statusbar.py \
  --dry-run \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

Expected shape:

```text
 42%  ▁▂▃▄▃▃▄▅▆▅▄▃▂▁▂▃▄▃▃▄▅▆▅▄
42%  ▃▄▃▃▄▅▆▅▄▁▂▃▄▃▃▄
42%  ▃▃▄▅▆▅▄▁▂▃▄▃▃▄
42%  ▃▄▅▆▅▄▁▂▃▄▃▃▄
42%  ▅▆▅▄▁▂▃▄▃▃▄
42%
```

To test fallback rendering without touching live cache:

```sh
rm -f "$PWD/tmp/gpu_usage.json"
python3 scripts/iterm2_gpu_statusbar.py \
  --dry-run \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

Expected output:

```text
--% ▁▁▁▁
--%
```

## Stale Cache Test

```sh
python3 - <<'PY'
import json, pathlib, time
path = pathlib.Path("tmp/gpu_usage_stale.json")
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps({
    "schema_version": 1,
    "metric": "gpu",
    "usage_percent": 42,
    "timestamp": time.time() - 3600,
    "stale_after_seconds": 18
}) + "\n")
PY

python3 scripts/iterm2_gpu_statusbar.py \
  --dry-run \
  --cache-path "$PWD/tmp/gpu_usage_stale.json"
```

Expected output:

```text
--% ▁▁▁▁
--%
```

## Rendered Plist Dry Run

This renders a launchd plist into `tmp/` only:

```sh
REPO_DIR="$PWD"
mkdir -p tmp
sed \
  -e "s#__INSTALL_DIR__#$REPO_DIR#g" \
  -e "s#__HOME__#$PWD/tmp/home#g" \
  templates/dev.local.iterm2-gpu-collector.plist \
  > tmp/dev.local.iterm2-gpu-collector.plist
plutil -lint tmp/dev.local.iterm2-gpu-collector.plist
```

Do not run `launchctl bootstrap` in this repo-local review phase.

## CPU and Battery Overhead Checks

Baseline one-shot cost:

```sh
/usr/bin/time -l python3 scripts/gpu_collector.py \
  --once \
  --cache-path "$PWD/tmp/gpu_usage.json"
```

Short collector run:

```sh
python3 scripts/gpu_collector.py \
  --interval 2.5 \
  --cache-path "$PWD/tmp/gpu_usage.json" &
PID=$!
sleep 20
ps -o pid,ppid,%cpu,%mem,etime,command -p "$PID"
kill "$PID"
wait "$PID" 2>/dev/null || true
```

Wakeups and energy impact can be inspected with Activity Monitor:

1. Open Activity Monitor.
2. On the CPU tab, search for `python3`.
3. Confirm the collector stays near idle between 2.5 second samples.
4. On the Energy tab, inspect Energy Impact during a 5 to 10 minute run.

Optional command-line diagnostic, requires sudo:

```sh
sudo powermetrics --samplers tasks,gpu_power -n 5 -i 2000
```

This is for validation only. The default collector does not require sudo.

## Acceptance Checklist

- `py_compile` passes.
- plist template lints.
- icon PNGs are present at 16x17 and 32x34.
- collector writes a JSON cache under `tmp/`.
- status renderer reads the cache under `tmp/`.
- status renderer returns variable-length strings.
- collector stores smoothed display values and up to 24 recent history samples.
- missing cache renders `--% ▁▁▁▁` and `--%`.
- stale cache renders `--% ▁▁▁▁` and `--%`.
- no command writes to live iTerm2, LaunchAgents, or home cache paths during dry-run.
