# Third-party licences

reelcut is MIT-licensed. This file lists the licences of everything it depends on, downloads or vendors, with a link to each project. Python licences come from the installed package metadata (`License-Expression`, else the licence classifiers), npm licences from each package's `package.json`, and model licences from the files at the pinned revision. All entries were checked on 2026-10-24. Nothing is marked UNVERIFIED.

Three items matter for commercial use: Remotion (free only for individuals, companies of up to 3 employees, non-profits and evaluation), the ACE-Step weights (MIT, commercial output allowed per the model card), and CrisperWhisper (not shipped; CC BY-NC 4.0, non-commercial). The README's Licences section summarises them.

## Rendering

| Component | Version | Licence | Link | Notes |
|---|---|---|---|---|
| Remotion (`remotion`, `@remotion/cli`, and the `@remotion/*` packages they pull in: renderer, bundler, player, media, web-renderer, studio, compositor binaries) | 4.0.538 | Remotion License (source-available, not OSI open source) | [remotion.dev/license](https://www.remotion.dev/license) | Checked 2026-10-24: remotion.dev/license redirects to `LICENSE.md` on the main branch of remotion-dev/remotion, and that file is byte-identical to `node_modules/remotion/LICENSE.md` of the pinned 4.0.538. Free License: individuals, for-profit organisations with up to 3 employees, non-profits and not-for-profits, and evaluation before commercial use, for creating videos and images, commercially or not. Copying or modifying Remotion to sell or relicense a derivative is not allowed. Everyone else needs a Company License ([remotion.pro/license](https://www.remotion.pro/license)). The file says the licence changes slightly in Remotion 5.0. |
| `@remotion/captions`, `@remotion/fonts`, `@remotion/layout-utils` | 4.0.538 | MIT | [github.com/remotion-dev/remotion](https://github.com/remotion-dev/remotion) | Their own `package.json` declares MIT. |
| FFmpeg inside `@remotion/compositor-darwin-arm64` (and the other platform packages) | n7.1 | GPL (built with `--enable-gpl`, libx264, libx265, libfdk-aac) | [ffmpeg.org/legal.html](https://ffmpeg.org/legal.html) | Remotion's own build, downloaded by npm into the renderer; reelcut does not redistribute it. |
| Chrome Headless Shell | 157.0.8080.0 (Remotion build) | BSD-3-Clause (Chromium) plus the third-party notices in its `LICENSE.headless_shell` | [chromium.org](https://www.chromium.org/Home/) | Downloaded by `remotion browser ensure` during `reelcut setup`; not redistributed. |
| React, React DOM | 19.2.3 | MIT | [github.com/facebook/react](https://github.com/facebook/react) | |
| Inter font via `@fontsource/inter` | 5.3.0 | SIL Open Font License 1.1 | [github.com/rsms/inter](https://github.com/rsms/inter) | Verified from `node_modules/@fontsource/inter/LICENSE`. Bundled into every render as the default caption and title font. |

The renderer's full npm tree is 285 packages: 222 MIT, 17 ISC, 11 BSD-2-Clause, 7 Apache-2.0, 6 MPL-2.0 (`lightningcss` and `mediabunny` with its encoders), 5 BSD-3-Clause, 2 Unlicense (`memfs`, `fs-monkey`), 1 each of 0BSD, CC-BY-4.0 (`caniuse-lite`, data), OFL-1.1 (Inter), Python-2.0 and PSF-2.0 (`argparse`), and the Remotion packages above. Counted from the installed `node_modules` of the renderer `reelcut setup` installs; `renderer/package-lock.json` pins every version.

Renderer development only (not installed by `setup`'s users unless they run tests): `typescript` 5.9.3 Apache-2.0 ([github.com/microsoft/TypeScript](https://github.com/microsoft/TypeScript)), `vitest` 5.0.5 MIT ([vitest.dev](https://vitest.dev)), `json-schema-to-typescript` 16.0.0 MIT ([github.com/bcherny/json-schema-to-typescript](https://github.com/bcherny/json-schema-to-typescript)), `@types/react` 19.2.7 MIT ([github.com/DefinitelyTyped/DefinitelyTyped](https://github.com/DefinitelyTyped/DefinitelyTyped)).

## Contact sheets

| Component | Version | Licence | Link | Notes |
|---|---|---|---|---|
| DejaVu Sans, cut to Latin (`src/reelcut/look/fonts/DejaVuSans-Latin.ttf`) | 2.35 | Bitstream Vera licence (DejaVu changes public domain) | [github.com/dejavu-fonts/dejavu-fonts](https://github.com/dejavu-fonts/dejavu-fonts) | Licence vendored next to the font as `LICENSE-DejaVu.txt`. Subset with fontTools `pyftsubset` from the `DejaVuSans.ttf` that matplotlib 3.11.2 ships (SHA-256 `3fdf69ca...0d22`); the licence allows modified copies whose names do not contain "Bitstream" or "Vera". |

## Python: direct dependencies

Pinned exactly in `pyproject.toml`.

| Package | Version | Licence | Link |
|---|---|---|---|
| typer | 0.27.3 | MIT | [github.com/fastapi/typer](https://github.com/fastapi/typer) |
| rich | 15.0.0 | MIT | [github.com/Textualize/rich](https://github.com/Textualize/rich) |
| pydantic | 2.14.1 | MIT | [github.com/pydantic/pydantic](https://github.com/pydantic/pydantic) |
| tomli-w | 1.2.0 | MIT | [github.com/hukkin/tomli-w](https://github.com/hukkin/tomli-w) |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [numpy.org](https://numpy.org) |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | [github.com/opencv/opencv-python](https://github.com/opencv/opencv-python) |
| scenedetect | 0.7.2 | BSD-3-Clause | [scenedetect.com](https://www.scenedetect.com) |
| mediapipe | 1.1.1 | Apache-2.0 | [github.com/google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) |
| onnxruntime | 1.31.0 | MIT | [onnxruntime.ai](https://onnxruntime.ai) |
| rapidfuzz | 3.14.6 | MIT | [github.com/rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) |
| librosa | 1.0.0 | ISC | [librosa.org](https://librosa.org) |
| soundfile | 0.14.0 | BSD-3-Clause | [github.com/bastibe/python-soundfile](https://github.com/bastibe/python-soundfile) |
| pillow | 13.0.0 | MIT-CMU | [python-pillow.github.io](https://python-pillow.github.io) |
| platformdirs | 4.13.5 | MIT | [github.com/tox-dev/platformdirs](https://github.com/tox-dev/platformdirs) |
| mlx-whisper (extra `mac`) | 0.4.3 | MIT | [github.com/ml-explore/mlx-examples](https://github.com/ml-explore/mlx-examples/tree/main/whisper) |
| faster-whisper (extra `cpu`) | 1.2.1 | MIT | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |

## Python: packages these pull in

Every other package in the runtime closure of `uv.lock` with both extras (`uv export --no-dev --extra cpu --extra mac`), with its PyPI page as the link (`https://pypi.org/project/<name>/`). Two are platform-only and not installed on macOS: `colorama` (Windows) and `httpx2-jsfetch` (Emscripten); their licences come from PyPI.

| Package | Version | Licence |
|---|---|---|
| [absl-py](https://pypi.org/project/absl-py/) | 2.5.1 | Apache-2.0 |
| [annotated-doc](https://pypi.org/project/annotated-doc/) | 0.0.5 | MIT |
| [annotated-types](https://pypi.org/project/annotated-types/) | 0.8.0 | MIT |
| [anyio](https://pypi.org/project/anyio/) | 4.15.1 | MIT |
| [av](https://pypi.org/project/av/) | 19.0.2 | BSD-3-Clause |
| [certifi](https://pypi.org/project/certifi/) | 2026.10.23 | MPL-2.0 |
| [cffi](https://pypi.org/project/cffi/) | 2.1.1 | MIT-0 |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | 3.5.2 | MIT |
| [click](https://pypi.org/project/click/) | 8.5.0 | BSD-3-Clause |
| [cloudpickle](https://pypi.org/project/cloudpickle/) | 3.1.2 | BSD |
| [colorama](https://pypi.org/project/colorama/) | 0.4.6 | BSD (Windows only) |
| [contourpy](https://pypi.org/project/contourpy/) | 1.4.0 | BSD-3-Clause |
| [ctranslate2](https://pypi.org/project/ctranslate2/) | 4.8.3 | MIT |
| [cycler](https://pypi.org/project/cycler/) | 0.12.1 | BSD |
| [decorator](https://pypi.org/project/decorator/) | 5.3.1 | BSD-2-Clause |
| [filelock](https://pypi.org/project/filelock/) | 4.2.4 | MIT |
| [flatbuffers](https://pypi.org/project/flatbuffers/) | 25.12.19 | Apache-2.0 |
| [fonttools](https://pypi.org/project/fonttools/) | 4.67.0 | MIT |
| [fsspec](https://pypi.org/project/fsspec/) | 2026.9.0 | BSD-3-Clause |
| [h11](https://pypi.org/project/h11/) | 0.16.0 | MIT |
| [hf-xet](https://pypi.org/project/hf-xet/) | 1.7.0 | Apache-2.0 |
| [httpcore2](https://pypi.org/project/httpcore2/) | 2.16.0 | BSD-3-Clause |
| [httpx2](https://pypi.org/project/httpx2/) | 2.16.0 | BSD-3-Clause |
| [httpx2-jsfetch](https://pypi.org/project/httpx2-jsfetch/) | 1.0 | BSD-3-Clause (Emscripten only) |
| [huggingface-hub](https://pypi.org/project/huggingface-hub/) | 2.3.0 | Apache-2.0 |
| [idna](https://pypi.org/project/idna/) | 3.20 | BSD-3-Clause |
| [jinja2](https://pypi.org/project/jinja2/) | 3.1.6 | BSD |
| [joblib](https://pypi.org/project/joblib/) | 1.6.0 | BSD-3-Clause |
| [kiwisolver](https://pypi.org/project/kiwisolver/) | 1.5.1 | BSD |
| [lazy-loader](https://pypi.org/project/lazy-loader/) | 0.6 | BSD-3-Clause |
| [llvmlite](https://pypi.org/project/llvmlite/) | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception |
| [markdown-it-py](https://pypi.org/project/markdown-it-py/) | 4.2.0 | MIT |
| [markupsafe](https://pypi.org/project/markupsafe/) | 3.0.4 | BSD-3-Clause |
| [matplotlib](https://pypi.org/project/matplotlib/) | 3.11.2 | PSF-based matplotlib licence |
| [mdurl](https://pypi.org/project/mdurl/) | 0.1.2 | MIT |
| [mlx](https://pypi.org/project/mlx/) | 0.32.4 | MIT |
| [mlx-metal](https://pypi.org/project/mlx-metal/) | 0.32.4 | MIT |
| [more-itertools](https://pypi.org/project/more-itertools/) | 11.2.1 | MIT |
| [mpmath](https://pypi.org/project/mpmath/) | 1.3.0 | BSD |
| [msgpack](https://pypi.org/project/msgpack/) | 1.2.3 | Apache-2.0 |
| [narwhals](https://pypi.org/project/narwhals/) | 2.27.1 | MIT |
| [networkx](https://pypi.org/project/networkx/) | 3.7 | BSD-3-Clause |
| [numba](https://pypi.org/project/numba/) | 0.68.0 | BSD |
| [opencv-contrib-python](https://pypi.org/project/opencv-contrib-python/) | 5.0.0.93 | Apache-2.0 |
| [opencv-python](https://pypi.org/project/opencv-python/) | 5.0.0.93 | Apache-2.0 |
| [packaging](https://pypi.org/project/packaging/) | 26.3 | Apache-2.0 OR BSD-2-Clause |
| [pooch](https://pypi.org/project/pooch/) | 1.9.0 | BSD-3-Clause |
| [protobuf](https://pypi.org/project/protobuf/) | 7.36.2 | BSD-3-Clause |
| [pycparser](https://pypi.org/project/pycparser/) | 3.12 | BSD-3-Clause |
| [pydantic-core](https://pypi.org/project/pydantic-core/) | 2.50.1 | MIT |
| [pygments](https://pypi.org/project/pygments/) | 2.21.0 | BSD-2-Clause |
| [pyparsing](https://pypi.org/project/pyparsing/) | 3.3.3 | MIT |
| [python-dateutil](https://pypi.org/project/python-dateutil/) | 3.0.0 | BSD AND Apache-2.0 (dual-licensed parts) |
| [pyyaml](https://pypi.org/project/pyyaml/) | 6.0.3 | MIT |
| [regex](https://pypi.org/project/regex/) | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| [requests](https://pypi.org/project/requests/) | 2.34.2 | Apache-2.0 |
| [scikit-learn](https://pypi.org/project/scikit-learn/) | 1.9.1 | BSD-3-Clause |
| [scipy](https://pypi.org/project/scipy/) | 1.18.1 | BSD |
| [setuptools](https://pypi.org/project/setuptools/) | 84.2.1 | MIT |
| [shellingham](https://pypi.org/project/shellingham/) | 1.5.4 | ISC |
| [six](https://pypi.org/project/six/) | 1.17.0 | MIT |
| [sounddevice](https://pypi.org/project/sounddevice/) | 0.5.6 | MIT |
| [soxr](https://pypi.org/project/soxr/) | 1.1.0 | LGPL-2.1-or-later |
| [sympy](https://pypi.org/project/sympy/) | 1.14.0 | BSD |
| [threadpoolctl](https://pypi.org/project/threadpoolctl/) | 3.7.0 | BSD-3-Clause |
| [tiktoken](https://pypi.org/project/tiktoken/) | 0.14.0 | MIT |
| [tokenizers](https://pypi.org/project/tokenizers/) | 0.23.3 | Apache-2.0 |
| [torch](https://pypi.org/project/torch/) | 2.14.1 | BSD-3-Clause and others (Apache-2.0, BSD-2-Clause, BSL-1.0, MIT, LLVM-exception parts) |
| [tqdm](https://pypi.org/project/tqdm/) | 4.70.1 | MPL-2.0 AND MIT |
| [truststore](https://pypi.org/project/truststore/) | 0.10.5 | MIT |
| [typing-extensions](https://pypi.org/project/typing-extensions/) | 4.16.0 | PSF-2.0 |
| [typing-inspection](https://pypi.org/project/typing-inspection/) | 0.4.4 | MIT |
| [tzdata](https://pypi.org/project/tzdata/) | 2026.5 | Apache-2.0 |
| [urllib3](https://pypi.org/project/urllib3/) | 2.8.0 | MIT |

All are permissive except three weak-copyleft libraries that reelcut uses unmodified, as installed packages: `certifi` and `tqdm` (MPL-2.0) and `soxr` (LGPL-2.1-or-later). None restricts commercial use.

## Python: development only

From the `dev` dependency group; not installed by `uv tool install`.

| Package | Version | Licence | Link |
|---|---|---|---|
| ruff | 0.17.2 | MIT | [github.com/astral-sh/ruff](https://github.com/astral-sh/ruff) |
| pyright | 1.1.414 | MIT | [github.com/microsoft/pyright](https://github.com/microsoft/pyright) |
| pytest | 9.1.1 | MIT | [pytest.org](https://pytest.org) |
| pytest-cov | 7.1.0 | MIT | [github.com/pytest-dev/pytest-cov](https://github.com/pytest-dev/pytest-cov) |
| hypothesis | 6.170.9 | MPL-2.0 | [hypothesis.works](https://hypothesis.works) |
| pre-commit | 4.7.0 | MIT | [pre-commit.com](https://pre-commit.com) |
| PyYAML | 6.0.3 | MIT | [pyyaml.org](https://pyyaml.org) |

## Models and weights

Downloaded by `reelcut setup` into the cache; none is redistributed in this repository except the RNNoise model.

| Model | Licence | Link | Notes |
|---|---|---|---|
| Whisper large-v3-turbo, CTranslate2 conversion `dropbox-dash/faster-whisper-large-v3-turbo` @ `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` (faster-whisper) | MIT | [huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo) | From the repository's `license:mit` tag. Upstream [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) is MIT. |
| Whisper large-v3-turbo, MLX conversion `mlx-community/whisper-large-v3-turbo` @ `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` (mlx-whisper) | MIT (upstream) | [huggingface.co/mlx-community/whisper-large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo) | The conversion repository states no licence of its own; the upstream OpenAI weights it converts are MIT. |
| Silero VAD `silero_vad.onnx` v6.2.3 | MIT | [github.com/snakers4/silero-vad](https://github.com/snakers4/silero-vad) | From `LICENSE` at tag v6.2.3. SHA-256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`. |
| MediaPipe BlazeFace full range, `blaze_face_full_range.tflite` float16 version 1 | Apache-2.0 | [MediaPipe face detector guide](https://ai.google.dev/edge/mediapipe/solutions/vision/face_detector) | From the official model card ("MediaPipe BlazeFace Model Card (Full Range)"): "Licensed under Apache License, Version 2.0". SHA-256 `3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b`. |
| OpenCV Zoo YuNet `face_detection_yunet_2023mar.onnx` (face-detection fallback) | MIT | [github.com/opencv/opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | From `models/face_detection_yunet/LICENSE` and its README at commit `48b10fa505aeb51fbd127fc60a5c660040e823b7`. SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`. |
| ACE-Step 1.5 weights `ACE-Step/Ace-Step1.5` @ `19671f406d603126926c1b7e2adc169acbcade22` (DiT `acestep-v15-turbo`, VAE, text encoder, 5 Hz LM 1.7B) | MIT | [huggingface.co/ACE-Step/Ace-Step1.5](https://huggingface.co/ACE-Step/Ace-Step1.5) | The repository has no LICENSE file; its model card declares `license: mit` in the front matter and "License: MIT" in the body, and says the generated music may be used commercially. The bundled Qwen3-Embedding-0.6B text encoder is Apache-2.0 upstream ([Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)). `reelcut setup --music` reads the licence from the downloaded files, prints it and records it in `<cache>/envs/ace-step/install.json`; every generated `music.json` copies it. |
| RNNoise model `sh.rnnn` ("somnolent-hogwash", speech in recording noise) | Not subject to copyright, per the repository README | [github.com/GregorR/rnnoise-models](https://github.com/GregorR/rnnoise-models) | At commit `3eee541a283fd3b8f81b85b1748e3b9ccbefa04d`. Vendored in `src/reelcut/audio/models/sh.rnnn` (SHA-256 `70bb6685eb0c2a1d18e2918dca3fbfbd39317010b1802eb1b6ea73a92f3fdec0`) for the ffmpeg `arnndn` fallback. |
| CrisperWhisper `nyralabs/CrisperWhisper` | CC BY-NC 4.0 (non-commercial) | [huggingface.co/nyralabs/CrisperWhisper](https://huggingface.co/nyralabs/CrisperWhisper) | From the repository's `license:cc-by-nc-4.0` tag and card front matter (the repository moved from `nyrahealth/`). Not shipped or downloaded in v0.1.0; see ROADMAP.md. |

## ACE-Step environment

`reelcut setup --music` installs ACE-Step into its own environment (`<cache>/envs/ace-step`, `uv sync --frozen` against ACE-Step's lock file), never into reelcut's.

| Component | Version | Licence | Link | Notes |
|---|---|---|---|---|
| ACE-Step 1.5 source `ace-step/ACE-Step-1.5` | `ca1e85fe9430179831e6bc6be790c332190a3866` | MIT | [github.com/ace-step/ACE-Step-1.5](https://github.com/ace-step/ACE-Step-1.5) | From `LICENSE` at that commit. |
| Its locked Python packages | 125 packages | Mostly MIT, Apache-2.0 and BSD | ACE-Step's `uv.lock` | Counted from the installed environment's metadata. Four needed a closer look: `torchao` 0.16.0 (no metadata licence; [pytorch/ao](https://github.com/pytorch/ao) is BSD-3-Clause), `sentencepiece` 0.2.1 (no metadata licence; [google/sentencepiece](https://github.com/google/sentencepiece) is Apache-2.0), `frozendict` 2.4.7 (LGPLv3, used unmodified), and `pytorch-wavelets` 1.3.0 (classifier "Free To Use But Restricted"; [its LICENSE](https://github.com/fbcotter/pytorch_wavelets/blob/master/LICENSE) is MIT for the DWT code, while the DTCWT parts carry the conditions of Nick Kingsbury's original MATLAB toolbox; ACE-Step's `dcw_*` modules use only the DWT classes). |

## System tools

| Tool | Version | Licence | Link | Notes |
|---|---|---|---|---|
| FFmpeg | system (9.0.1 on the build machine) | LGPL-2.1+ or GPL-2+ depending on the build | [ffmpeg.org/legal.html](https://ffmpeg.org/legal.html) | reelcut calls the system `ffmpeg` binary and does not distribute it. Homebrew's build is GPL. |
| DeepFilterNet (`deep-filter` binary) | 0.5.6 | MIT or Apache-2.0, at your option | [github.com/Rikorose/DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) | From the repository's `LICENSE`, `LICENSE-MIT` and `LICENSE-APACHE`. The release binary embeds the DeepFilterNet3 model from the same repository. `reelcut setup` downloads it into the cache and checks its SHA-256; it is not redistributed. |
| Node.js and npm | 22.13+ or 24+ | MIT (Node.js), Artistic-2.0 (npm) | [nodejs.org](https://nodejs.org) | Installed by the user; runs the Remotion CLI. |
| uv | 0.5.21 on the build machine | MIT OR Apache-2.0 | [github.com/astral-sh/uv](https://github.com/astral-sh/uv) | Installs reelcut and the ACE-Step environment. |
| sips | sips-316 (macOS 27.0.1) | Part of macOS | [developer.apple.com](https://developer.apple.com) | Decodes HEIC and HEIF photos to PNG during ingest on macOS. |
| libheif `heif-convert` | optional; not verified on the build machine | LGPL-3.0 (libheif), MIT (the example tools) | [github.com/strukturag/libheif](https://github.com/strukturag/libheif) | Decodes HEIC and HEIF on Linux when installed (`apt install libheif-examples`). reelcut runs the binary and does not distribute it. pillow-heif was not used because its binary wheels bundle libx265 (GPL-2.0). |
