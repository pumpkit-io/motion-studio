# HDR footage is tone-mapped with VideoToolbox `scale_vt` on macOS

Phone footage is often HLG or PQ HDR and must become BT.709 SDR at ingest. The usual ffmpeg chain is `zscale` + `tonemap`, but Homebrew's ffmpeg (9.0.1 on the build machine) is compiled without zimg, so `zscale` is missing. On macOS, ingest uses ffmpeg's `scale_vt` filter with `color_transfer=bt709` and BT.709 matrix and primaries, which Homebrew's build includes. Where `zscale` is available (typically Linux), ingest uses `zscale` + `tonemap`. Where neither is available, it falls back to the `colorspace` filter and warns, because that path does not tone-map properly.

## Considered Options

- Installing ffmpeg from the `homebrew-ffmpeg` tap with zimg. Rejected: it replaces the creator's system ffmpeg and builds from source.
- Downloading a static ffmpeg build into the motion-studio cache. Rejected for v0.1.0: one more binary whose provenance and licence would need tracking.
