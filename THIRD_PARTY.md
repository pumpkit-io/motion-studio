# Third-party licences

reelcut is MIT-licensed. This file lists the licences of what it depends on and downloads. Entries marked UNVERIFIED have not been checked against the exact files reelcut uses yet; each ticket that adds a dependency verifies it here.

## Rendering

| Component | Version | Licence | Notes |
|---|---|---|---|
| Remotion (`remotion`, `@remotion/*`) | 4.0.538 | Remotion License (not OSI open source) | Verified from `node_modules/remotion/LICENSE.md` on 2026-10-24. Free for individuals, for-profit organisations with up to 3 employees, non-profits, and evaluation. Larger for-profit organisations need a Company License from remotion.pro. The licence notes that it changes slightly in Remotion 5.0. |
| React, React DOM | 19.2.3 | MIT | |

## Python core

| Package | Version | Licence (PyPI metadata) |
|---|---|---|
| typer | 0.27.3 | MIT |
| rich | 15.0.0 | MIT |
| pydantic | 2.14.1 | MIT |
| tomli-w | 1.2.0 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 |
| scenedetect | 0.7.2 | BSD-3-Clause |
| mediapipe | 1.1.1 | Apache-2.0 |
| onnxruntime | 1.31.0 | MIT |
| rapidfuzz | 3.14.6 | MIT |
| librosa | 1.0.0 | ISC |
| soundfile | 0.14.0 | BSD-3-Clause |
| pillow | 13.0.0 | MIT-CMU |
| platformdirs | 4.13.5 | MIT |

## Python extras

| Package | Extra | Version | Licence (PyPI metadata) |
|---|---|---|---|
| mlx-whisper | `mac` | 0.4.3 | MIT |
| faster-whisper | `cpu` | 1.2.1 | MIT |

## Models and weights

| Model | Licence | Status |
|---|---|---|
| Whisper large-v3-turbo (MLX and CTranslate2 conversions) | MIT (OpenAI Whisper) | UNVERIFIED for the exact converted repositories `reelcut setup` downloads |
| Silero VAD | MIT | UNVERIFIED |
| MediaPipe BlazeFace | Apache-2.0 | UNVERIFIED |
| ACE-Step 1.5 weights | Unknown | UNVERIFIED. `reelcut setup --music` prints the licence of the exact weights it downloads, and every `music.json` records it. |
| CrisperWhisper | Believed CC BY-NC 4.0 (non-commercial) | Not shipped in v0.1.0; see ROADMAP.md |

## System tools

| Tool | Licence | Notes |
|---|---|---|
| FFmpeg | LGPL-2.1+ or GPL-2+ depending on the build | reelcut calls the system `ffmpeg` binary and does not distribute it. Homebrew's build is GPL. |
| DeepFilterNet | MIT or Apache-2.0 | UNVERIFIED; added by the ingest ticket |
