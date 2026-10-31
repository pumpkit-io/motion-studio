# Roadmap

Ideas beyond v0.1.0, in no particular order.

## Editing and analysis

- FCPXML / OpenTimelineIO export for finishing in DaVinci Resolve or Final Cut. The timeline is the hook for it.
- Optional Gemini video pass for "visually interesting moment" detection (opt-in, paid).
- Multi-speaker (diarization) and podcast clipping.
- Licensed SFX library support (whooshes, pops) with the same licence tracking as music. Product videos need it most: whooshes on cuts were left out of the first launch video for lack of one.
- Smoothed face tracking within long single-shot segments.
- Auto-chaptering a long recording into several shorts.
- More languages via `lang/*.toml` contributions.

## Product videos

- Vertical product videos (9x16 and 4x5). Product EDLs render in 16x9 only, and `plan validate` rejects other formats with `product_format`.
- A phone device frame, for mobile apps.
- A GIF mascot for the logo outro. `[brand] mascot` takes a sprite sheet with frame timings only.

## Speech-to-text backends

- `parakeet-mlx` (Parakeet TDT 0.6B v3, English and Italian) as an optional Apple Silicon backend.
- CrisperWhisper as an optional verbatim, filler-aware backend. Its model card licence is CC BY-NC 4.0 (non-commercial; checked 2026-10-24 at `nyralabs/CrisperWhisper`), so it must stay off by default with a warning. v0.1.0 accepts `fillers_backend = "crisper"` in config and fails with "not implemented in v0.1.0".

## Packaging and interfaces

- Claude Code plugin packaging for the motion-studio skills.
- Optional MCP server wrapping the CLI.
