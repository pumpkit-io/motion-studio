# Roadmap

Ideas beyond v0.1.0, in no particular order.

## Editing and analysis

- FCPXML / OpenTimelineIO export for finishing in DaVinci Resolve or Final Cut. The timeline is the hook for it.
- Optional Gemini video pass for "visually interesting moment" detection (opt-in, paid).
- Multi-speaker (diarization) and podcast clipping.
- Licensed SFX library support (whooshes, pops) with the same licence tracking as music.
- Smoothed face tracking within long single-shot segments.
- Auto-chaptering a long recording into several shorts.
- More languages via `lang/*.toml` contributions.

## Speech-to-text backends

- `parakeet-mlx` (Parakeet TDT 0.6B v3, English and Italian) as an optional Apple Silicon backend.
- CrisperWhisper as an optional verbatim, filler-aware backend. Its model card licence is CC BY-NC 4.0 (non-commercial; checked 2026-10-24 at `nyralabs/CrisperWhisper`), so it must stay off by default with a warning. v0.1.0 accepts `fillers_backend = "crisper"` in config and fails with "not implemented in v0.1.0".

## Packaging and interfaces

- Claude Code plugin packaging for the motion-studio skills.
- Optional MCP server wrapping the CLI.
