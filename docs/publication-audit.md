# Luna 0.6.0 publication audit

Reviewed on 2026-10-07. This supersedes the 0.4.1 audit, whose subject (a redistributed Python
runtime) no longer exists.

## What Luna redistributes

The release assets contain:

- Luna's own code (MIT): the Electron app, the backend in `resources\backend`, the runtime lock and
  the scripts that install and check it;
- Electron 43.4.0 with Chromium (`LICENSE.electron.txt`, `LICENSES.chromium.html` in the install).
  Its LGPL `ffmpeg.dll` is covered by `Electron-media-sources.zip`, attached to the release unchanged
  from 0.4.1 (same Electron and FFmpeg revision);
- uv 0.12.23 (`uv.exe`, MIT OR Apache-2.0, both licence texts in `resources\runtime\uv`), unmodified
  and checked against the SHA-256 of uv's GitHub release;
- three pure-Python wheels built from their PyPI source archives without modification: fairseq 0.12.2
  (MIT), antlr4-python3-runtime 4.8 (BSD-3-Clause) and sox 1.5.0 (BSD-3-Clause). Each wheel carries
  its licence in its `.dist-info`;
- the brand fonts Fraunces, Commissioner and Spline Sans Mono (SIL OFL 1.1, licence texts beside the
  files in `app/static/brand/fonts`).

It no longer contains CPython, PyTorch, the NVIDIA CUDA and cuDNN libraries inside PyTorch's wheel,
SoundFile/libsndfile, or any other Python distribution. Each Luna installation downloads those itself
from their publishers (python-build-standalone through uv, the Python Package Index, PyTorch's
download server) under their own licences. The runtime source archive, the 121-package licence
inventory and the CUDA notices that 0.4.1 attached are therefore not part of this release.

The source and installer contain no voice recordings, voice packs, user data, model caches or
generated audio. New installations acquire pinned official Qwen packs through Luna. Upgrades preserve
existing local legacy voice files; they are not redistributed.

## The runtime each installation sets up

`packaging/runtime/uv.lock` fixes 96 wheels and their SHA-256 digests; Luna verifies each download
and uv verifies it again at install time. Versions are those of the reviewed 0.4.1 runtime, with
Python 3.12.15 in place of 3.12.13. Removed compared with 0.4.1, none of them imported by Luna: the
leftovers of the excluded Gradio demo (pandas, pytz, tzdata, typer, rich, markdown-it-py, mdurl,
Pygments, shellingham, brotli, orjson, pydub, semantic-version, tomlkit, httpx, httpcore,
cryptography), uvicorn's optional extras (httptools, websockets, watchfiles, python-dotenv),
tensorboardX, and, found by tracing all four engines through real generation, ffmpeg-python, loguru
and monotonic-alignment-search. llvmlite/numba, torchcrepe, faiss-cpu, scikit-learn, matplotlib and
onnxruntime stay: each is imported on a generation path.

Luna applies the same five source changes as 0.4.1, after installation and on the user's machine
(`packaging/runtime/apply_patches.py`): Python 3.12 dataclass defaults in fairseq and Hydra, Praat
imported only for RVC's unused `pm` mode, RVC's WAV input read with SoundFile instead of PyAV, and
Coqui's torchcodec import guard removed. Each file must match the pinned upstream hash before the
change and the reviewed hash after it. PyAV, Praat, torchcodec, Gradio and TensorBoard are not
installed.

## Advisory review and retained compatibility dependencies

The package versions are unchanged from 0.4.1, so its advisory review still applies:

- Accelerate 1.12.0: GHSA-4j2p-28q2-5m79, untrusted shard-index paths. Luna acquires only the
  hash-pinned official catalogue; arbitrary model URLs are rejected.
- Hydra 1.0.7: GHSA-2cp2-2r3c-7p7r, untrusted `instantiate` targets. Required by legacy Fairseq;
  Luna exposes no config-instantiation or arbitrary YAML endpoint.
- PyTorch 2.11.0: GHSA-rrmf-rvhw-rf47, `torch.jit.script`. Luna accepts no user Python or JIT
  source. Existing legacy pickle checkpoints remain trusted local inputs.
- Transformers 4.57.3: GHSA-69w3-r845-3855, GHSA-29pf-2h5f-8g72, GHSA-fgcw-684q-jj6r,
  GHSA-x9r9-c232-4q39 and GHSA-xrqw-3rrv-vx5w. Training, LightGlue, remote code and saving untrusted
  tokenizer templates are not exposed.
- Setuptools 78.1.0: GHSA-5rjg-fvgr-3xxf and GHSA-h35f-9h28-mq5c concern package downloads and source
  builds. Luna offers no package installation endpoint; its runtime setup installs only locked,
  hash-checked wheels with source builds disabled.

The loopback API requires a per-session token. The model downloader verifies each catalogue file.
Library deletion, export and reveal resolve registered outputs within their allowed roots.

## Release verification

On Windows 11 with an RTX 4080 SUPER (driver 617.14), from the built package with isolated data and
runtime folders: a real first-run setup (3.02 GB in about 1.5 minutes, 2 minutes 38 seconds to a
verified runtime), a cancelled and resumed setup across a restart, the switch from a stale runtime
with its removal, the no-GPU path (`CUDA_VISIBLE_DEVICES=-1`), real GPU generation with a Qwen
CustomVoice speaker, David (XTTS) and E-Girl (RVC) through the running app, Qwen cloning and all four
engines traced in-process, a second start with no download, and an installer upgrade from a build
carrying a bundled `resources\python` (under a throwaway app identity) that left no Python behind.
