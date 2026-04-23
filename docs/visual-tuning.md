# Visual Tuning Notes

## Default Presentation

The revised component uses iTerm2 `StatusBarComponent` icons plus variable-length plain text.

Default variants returned to iTerm2:

```text
 56%  ▁▂▃▄▅▄▃▂▃▄▅▆▅▄▃▂▃▄▅▄▃▂▃▄
56%  ▃▄▅▄▃▂▃▄▅▄▃▂▃▄▅▄
56%
```

Fallback variants:

```text
--% ▁▁▁▁
--%
```

iTerm2 chooses the longest string that fits. The icon is supplied separately through the public status bar icon API, so the text stays plain and avoids a boxed custom-widget feel.

## Icon

Assets:

- `assets/gpu-chip.png`: 16x17 px, scale 1
- `assets/gpu-chip@2x.png`: 32x34 px, scale 2

Design constraints:

- transparent background
- 2 point edge margin
- thin single-color stroke
- repo 1x asset is a 16x17 px pixel icon
- 2x asset is nearest-neighbor scaled to 32x34 for iTerm2 retina icon registration
- visible glyph constrained to a square footprint for symmetric left/right and top/bottom balance
- no filled badge, button, rounded text box, gradients, or decorative color

The icon data is embedded into `scripts/iterm2_gpu_statusbar.py` as base64 so live installation does not need extra asset files outside the approved paths.

## Sparkline Decision

The native CPU/RAM/Battery graph renderer is not exposed through the public Python API. A Unicode sparkline is the closest text-only compromise, but it can look less native depending on font, antialiasing, and status bar height.

Recommended default:

- Use icon + percent + sparkline.
- Keep `GPU` out of the returned text because the icon already provides the label.
- Disable sparkline only if local font rendering makes the block characters look heavier than native graphs.

## iTerm2 Layout Recommendations

These are profile-level UI recommendations; the installer does not change them.

- Layout algorithm: Stable Positioning.
- Size Multiple: `1`.
- Priority: `5` when matching CPU/RAM/Battery defaults; use `4` if GPU should disappear before battery in narrow windows.
- Minimum Width: `0`.
- Maximum Width: `200`.
- Placement: next to CPU/RAM/Battery, preferably after CPU and before memory if GPU is being watched for compute workloads.
- Spring/spacer: avoid adding a spacer between CPU/RAM/GPU/Battery. If the status bar has left/right groups, keep one spring outside the resource cluster rather than inside it.

Stable Positioning fits this component better than Tight Packing. The percent and sparkline change over time; Tight Packing can redistribute widths as text changes, making nearby components jump. Stable Positioning reserves predictable space using priority and size multiple, so updates look more like native resource graphs. A Size Multiple of `1` is the best default here because the component should blend into the native resource cluster rather than claim extra reserved width.

The sparkline history is padded to a stable 24-sample buffer and advances only when the displayed percent changes. The long variant also right-aligns the percent in a fixed four-character column before the graph. That keeps the component visually stable without forcing the whole text graph to scroll every collector tick.

For narrow status-bar allocations, the component also returns 16-block, 14-block, 13-block, 12-block, 8-block, and 4-block sparkline variants before the percent-only fallback. This keeps at least a small graph visible even if the component minimum width is still small. The percent and graph use a two-space gap so the value does not visually collide with the sparkline.

Recommended cluster:

```text
CPU | GPU | Memory | Battery
```

If sparkline is enabled:

```text
CPU | 56% ▁▂▃▄▅▄▃▂▃▄▅▆▅▄ | Memory | Battery
```

If the sparkline looks busy or visually heavier than native graphs, disable it and keep:

```text
CPU | 56% | Memory | Battery
```
