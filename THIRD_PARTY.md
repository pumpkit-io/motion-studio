# Third-party licences

reelcut is MIT-licensed. This file lists the licences of what it depends on and downloads. Entries marked UNVERIFIED have not been checked against the exact files reelcut uses yet; each ticket that adds a dependency verifies it here.

## Rendering

| Component | Version | Licence | Notes |
|---|---|---|---|
| Remotion (`remotion`, `@remotion/*`) | 4.0.538 | Remotion License (not OSI open source) | Verified from `node_modules/remotion/LICENSE.md` on 2026-10-24. Free for individuals, for-profit organisations with up to 3 employees, non-profits, and evaluation. Larger for-profit organisations need a Company License from remotion.pro. The licence notes that it changes slightly in Remotion 5.0. |
| React, React DOM | 19.2.3 | MIT | |
| Inter font via `@fontsource/inter` | 5.3.0 | SIL Open Font License 1.1 | Verified from `node_modules/@fontsource/inter/LICENSE` on 2026-10-24. Bundled into every render as the default caption and title font. |

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
| Whisper large-v3-turbo, CTranslate2 conversion `dropbox-dash/faster-whisper-large-v3-turbo` @ `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` (faster-whisper) | MIT | Verified 2026-10-24 from the repository's `license:mit` tag on Hugging Face. Upstream `openai/whisper-large-v3-turbo` is MIT. Downloaded by `reelcut setup`, not redistributed. |
| Whisper large-v3-turbo, MLX conversion `mlx-community/whisper-large-v3-turbo` @ `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` (mlx-whisper) | MIT (upstream) | Checked 2026-10-24: the conversion repository states no licence of its own (no tag, no licence in its README); the upstream `openai/whisper-large-v3-turbo` weights it converts are MIT. Downloaded by `reelcut setup`, not redistributed. |
| Silero VAD `silero_vad.onnx` v6.2.3 | MIT | Verified 2026-10-24 from `LICENSE` at tag v6.2.3 of snakers4/silero-vad. SHA-256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`. Downloaded by `reelcut setup`, not redistributed. |
| MediaPipe BlazeFace full range, `blaze_face_full_range.tflite` float16 version 1 | Apache-2.0 | Verified 2026-10-24 from the official model card ("MediaPipe BlazeFace Model Card (Full Range)", linked from the MediaPipe face detector guide): "Licensed under Apache License, Version 2.0". SHA-256 `3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b`. Downloaded by `reelcut setup`, not redistributed. |
| OpenCV Zoo YuNet `face_detection_yunet_2023mar.onnx` (face-detection fallback) | MIT | Verified 2026-10-24 from `models/face_detection_yunet/LICENSE` and its README at opencv_zoo commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`. SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. Downloaded by `reelcut setup`, not redistributed. |
| ACE-Step 1.5 weights | Unknown | UNVERIFIED. `reelcut setup --music` prints the licence of the exact weights it downloads, and every `music.json` records it. |
| CrisperWhisper | Believed CC BY-NC 4.0 (non-commercial) | Not shipped in v0.1.0; see ROADMAP.md |
| RNNoise model `sh.rnnn` ("somnolent-hogwash", speech in recording noise) | Not subject to copyright, per the README of GregorR/rnnoise-models | Verified 2026-10-24 at commit `3eee541a283fd3b8f81b85b1748e3b9ccbefa04d`. Vendored in `src/reelcut/audio/models/sh.rnnn` (SHA-256 `70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0`) for the ffmpeg `arnndn` fallback. |

## System tools

| Tool | Version | Licence | Notes |
|---|---|---|---|
| FFmpeg | system | LGPL-2.1+ or GPL-2+ depending on the build | reelcut calls the system `ffmpeg` binary and does not distribute it. Homebrew's build is GPL. |
| DeepFilterNet (`deep-filter` binary) | 0.5.6 | MIT or Apache-2.0, at your option | Verified from the repository's `LICENSE`, `LICENSE-MIT` and `LICENSE-APACHE` (Rikorose/DeepFilterNet) on 2026-10-24. The release binary embeds the DeepFilterNet3 model from the same repository. reelcut downloads it into its cache (`install_deep_filter`) and does not redistribute it. |
