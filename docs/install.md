# Install, Update, and Uninstall

These commands are intended for the approved live install/update flow.

## Repo Files

- `scripts/gpu_collector.py`
- `scripts/iterm2_gpu_statusbar.py`
- `assets/gpu-chip.png`
- `assets/gpu-chip@2x.png`
- `templates/dev.local.iterm2-gpu-collector.plist`
- `docs/design.md`
- `docs/install.md`
- `docs/verification.md`
- `docs/visual-tuning.md`

## Live Paths Used After Approval

When live installation is approved, files will be placed as follows:

| Repo file | Live destination |
| --- | --- |
| `scripts/iterm2_gpu_statusbar.py` | `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/iterm2_gpu_statusbar.py` |
| `templates/dev.local.iterm2-gpu-collector.plist` after placeholder substitution | `~/Library/LaunchAgents/dev.local.iterm2-gpu-collector.plist` |
| `scripts/gpu_collector.py` | `~/.cache/iterm2-gpu/scripts/gpu_collector.py` |
| collector cache output | `~/.cache/iterm2-gpu/gpu_usage.json` |
| collector stdout log | `~/.cache/iterm2-gpu/collector.out.log` |
| collector stderr log | `~/.cache/iterm2-gpu/collector.err.log` |

The GPU icon assets are stored in `assets/` for review and embedded as base64 in the AutoLaunch Python script. No separate live icon files are required.

## Install Sequence After Approval

Set variables:

```sh
REPO_DIR="$PWD"
AUTO_DIR="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch"
AGENT_DIR="$HOME/Library/LaunchAgents"
CACHE_DIR="$HOME/.cache/iterm2-gpu"
LABEL="dev.local.iterm2-gpu-collector"
```

Create directories:

```sh
mkdir -p "$AUTO_DIR" "$AGENT_DIR" "$CACHE_DIR/scripts"
```

Install the iTerm2 AutoLaunch script:

```sh
cp "$REPO_DIR/scripts/iterm2_gpu_statusbar.py" "$AUTO_DIR/iterm2_gpu_statusbar.py"
cp "$REPO_DIR/scripts/gpu_collector.py" "$CACHE_DIR/scripts/gpu_collector.py"
chmod 755 "$AUTO_DIR/iterm2_gpu_statusbar.py" "$CACHE_DIR/scripts/gpu_collector.py"
```

Render and install the launchd plist:

```sh
sed \
  -e "s#__INSTALL_DIR__#$CACHE_DIR#g" \
  -e "s#__HOME__#$HOME#g" \
  "$REPO_DIR/templates/dev.local.iterm2-gpu-collector.plist" \
  > "$AGENT_DIR/$LABEL.plist"
```

Validate the plist:

```sh
plutil -lint "$AGENT_DIR/$LABEL.plist"
```

Load the collector:

```sh
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENT_DIR/$LABEL.plist"
launchctl enable "gui/$(id -u)/$LABEL"
```

Restart iTerm2 or run `Scripts > AutoLaunch > iterm2_gpu_statusbar.py`. If your iTerm2 setup uses a custom scripts folder, place `iterm2_gpu_statusbar.py` in that AutoLaunch folder instead of the default path.

Then open iTerm2 Settings > Profiles > Session, enable Status Bar, configure it, and drag the custom `GPU` component into the active status bar.

Recommended profile layout:

- Layout algorithm: Stable Positioning.
- Size Multiple: `1`.
- Priority: `5`, or `4` if GPU should disappear before battery in narrow windows.
- Minimum Width: `0`.
- Maximum Width: `200`.
- Keep the resource cluster together, without a spring/spacer between CPU, GPU, memory, and battery.

## Update Sequence After Approval

Use the same variables from the install section before running these commands.

Unload the existing collector:

```sh
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
```

Copy the updated AutoLaunch script:

```sh
cp "$REPO_DIR/scripts/iterm2_gpu_statusbar.py" "$AUTO_DIR/iterm2_gpu_statusbar.py"
cp "$REPO_DIR/scripts/gpu_collector.py" "$CACHE_DIR/scripts/gpu_collector.py"
chmod 755 "$AUTO_DIR/iterm2_gpu_statusbar.py" "$CACHE_DIR/scripts/gpu_collector.py"
```

Re-render the plist if template or path changed:

```sh
sed \
  -e "s#__INSTALL_DIR__#$CACHE_DIR#g" \
  -e "s#__HOME__#$HOME#g" \
  "$REPO_DIR/templates/dev.local.iterm2-gpu-collector.plist" \
  > "$AGENT_DIR/$LABEL.plist"
```

Reload:

```sh
launchctl bootstrap "gui/$(id -u)" "$AGENT_DIR/$LABEL.plist"
launchctl enable "gui/$(id -u)/$LABEL"
```

Restart the iTerm2 Python script from the Scripts menu or restart iTerm2.

## Rollback and Uninstall

Unload the collector:

```sh
LABEL="dev.local.iterm2-gpu-collector"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
```

Remove installed files:

```sh
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
rm -f "$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch/iterm2_gpu_statusbar.py"
```

Remove runtime cache and logs if desired:

```sh
rm -rf "$HOME/.cache/iterm2-gpu"
```

Restart iTerm2. If the component still appears in a profile's status bar configuration, remove it from Settings > Profiles > Session > Configure Status Bar.

## Troubleshooting Paths

- AutoLaunch script: `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/iterm2_gpu_statusbar.py`
- LaunchAgent: `~/Library/LaunchAgents/dev.local.iterm2-gpu-collector.plist`
- Cache: `~/.cache/iterm2-gpu/gpu_usage.json`
- Collector stdout: `~/.cache/iterm2-gpu/collector.out.log`
- Collector stderr: `~/.cache/iterm2-gpu/collector.err.log`
- launchd state: `launchctl print gui/$(id -u)/dev.local.iterm2-gpu-collector`

If the status bar shows `--%`, check in this order:

1. Is the LaunchAgent loaded?
2. Is the cache file present and fresh?
3. Does `python3 scripts/gpu_collector.py --once --print --cache-path /tmp/iterm2-gpu-test.json` print a value?
4. Does `ioreg -r -c AGXAccelerator -d 1 -a` contain `PerformanceStatistics`?
5. Are there errors in `collector.err.log`?
