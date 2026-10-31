# Brand

- `logo.png`: your logo, used on titles (the path is `[brand] logo` in `motion-studio.toml`).
- `fonts/`: font files for captions and titles. Set `[captions] font` to a file here, or leave it as `TikTok Sans` (the default; `Inter` is also bundled). Product videos use Inter unless it names a file here.
- A wordmark image (SVG or PNG), for the logo outro of product videos. Set `[brand] wordmark` to its path, such as `library/brand/wordmark.svg`.
- A mascot sprite sheet and its frame-timing JSON, for the logo outro of product videos. Set `[brand] mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }`.

The timing JSON names the frame size, where each frame sits in the sheet and how long it shows, in playing order. `loops` is how many times the frames play before the last one holds; leave it out, or set 0, to loop forever. Other keys (such as `image`, `columns` or `rows`) are ignored.

```json
{
  "frame_width": 544,
  "frame_height": 416,
  "loops": 0,
  "frames": [
    { "x": 0, "y": 0, "ms": 600 },
    { "x": 544, "y": 0, "ms": 80 }
  ]
}
```

The mascot plays at these timings and is drawn without smoothing, so pixel art stays crisp. A logo outro without the wordmark, or without the mascot (unless the scene sets `"mascot": false`), fails `plan validate` with the `[brand]` key to set.

Paths are relative to the workspace. Brand colours live in `motion-studio.toml` under `[brand]` and `[captions]`.
