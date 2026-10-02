# Luna 0.4.1 publication audit

Reviewed on 2026-10-02. This supersedes the local-only 0.4.0 runtime review.

## Public payload

The source and public installer exclude voice recordings, voice packs, user data,
model caches and generated audio. New installations acquire pinned official Qwen
packs through Luna. Upgrades preserve existing local legacy voice files.

The old installed Python environment contained unrelated document tooling and
mixed package metadata. The public runtime is assembled from the 121 explicit
versions in `packaging/runtime-packages.json`. NumPy, pandas, setuptools,
typing-inspection, urllib3 and lxml use checksum-verified PyPI wheels. All remaining
wheel RECORD hashes were checked. Only two pre-existing modifications are allowed:
Fairseq/Hydra Python 3.12 dataclass default factories; their hashes and diffs are recorded.
Coqui permits Luna’s SoundFile IO without torchcodec. RVC receives two additional source patches: optional Praat import and SoundFile
WAV decoding without PyAV. Legacy voice generation is rechecked in the final package.

The runtime excludes artifact-tool-v2, unrelated document tooling, PyAV/FFmpeg,
Praat, Gradio, pip and test/build tools. Each included distribution has preserved
notices. LGPL/MPL sources, native audio build inputs and local patches accompany
the release. The libsndfile DLL comes from the SoundFile 0.14.0 pinned binary
submodule; its mpg123 build-path hash matches vcpkg 2024.12.16's source/patch set.
Native codec versions are libsndfile 1.2.2, FLAC 1.4.3, Ogg 1.3.5, Vorbis 1.3.7,
Opus 1.5.2, mpg123 1.32.9 and LAME 3.100. Source archive hashes/URLs are recorded
in `packaging/runtime-sources.json`. CUDA/cuDNN redistributable notices are retained.

## Advisory review and retained compatibility dependencies

PyPI package/version metadata was checked with the owner's permission. urllib3
was upgraded to 2.8.0 to resolve the returned advisories. This is not a claim that
all packaged dependencies are free of known advisories. The release retains:

- Accelerate 1.12.0: GHSA-4j2p-28q2-5m79, untrusted shard-index paths. Luna
  acquires only the hash-pinned official catalogue; arbitrary model URLs are rejected.
- Hydra 1.0.7: GHSA-2cp2-2r3c-7p7r, untrusted `instantiate` targets. Required by
  legacy Fairseq; Luna exposes no config-instantiation or arbitrary YAML endpoint.
- PyTorch 2.11.0: GHSA-rrmf-rvhw-rf47, `torch.jit.script`. Luna does not accept
  user-provided Python/JIT source. Existing legacy pickle checkpoints remain trusted
  local inputs; no claim of safe loading of untrusted pickle files is made.
- Transformers 4.57.3: GHSA-69w3-r845-3855, GHSA-29pf-2h5f-8g72,
  GHSA-fgcw-684q-jj6r, GHSA-x9r9-c232-4q39 and GHSA-xrqw-3rrv-vx5w.
  Affected training, LightGlue, custom remote generation and saving untrusted
  tokenizer templates are not exposed. Inference uses local pinned model files,
  no remote Python code and no arbitrary model-repository input.
- Setuptools 78.1.0: GHSA-5rjg-fvgr-3xxf and GHSA-h35f-9h28-mq5c concern
  package downloads/source builds. Retained for legacy imports; Luna offers no
  package installation/build endpoint and ships no pip.

The loopback API requires a per-session token. The model downloader verifies each
catalogue file. Library deletion/export/reveal operations resolve registered outputs
and enforce their allowed roots. The public runtime gate verifies all file hashes,
package pins and licence records before packaging. Review exceptions again when
changing model imports, adding arbitrary model acquisition, or updating the ML stack.

## Release verification

The 0.4.0 local package passed first-run, upgrade preservation (37 files), five real
GPU voice generations, long-text completion, preview/export/reveal/reuse/delete and
installed identity checks. The cleaned 0.4.1 package repeats real inference and
library checks; the release notes record final results. Release assets are assembled
with Instrumenta's shared manifest writer and verified against their actual SHA-256.
No source, model, recording or credential was sent for the package advisory lookup.

Final packaged validation: 47 Windows backend tests, 46 portable tests (one
Windows-only skip), two desktop file-action tests and five real CUDA generations
passed. Fast and High select distinct 0.6B/1.7B checkpoints. The 983-character
passage produced ten segments and 78.66 seconds. Clean first-run, the eleven
available voices with preserved local assets, preview, native WAV export,
reveal bridge, parameter reuse and deletion during playback passed.
