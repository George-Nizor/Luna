# Third-party notices — Luna 0.4.1

Luna application code is MIT. Electron, CPython and all included libraries retain
their own licences. The installer includes Electron's licence and Chromium notices,
CPython's licence, and `resources/python/THIRD_PARTY_LICENSES` with notices for the
121 reviewed Python distributions and their bundled native dependencies.
`resources/python/runtime-manifest.json` records the exact package versions.

Most dependencies use MIT, BSD or Apache-2.0. Coqui TTS and other MPL components
retain their source and notices. SoundFile/libsndfile, libsoxr, num2words, and
native audio codecs include LGPL components. The matching release provides
`Luna-0.4.1-runtime-sources.zip`: source archives, applicable build recipes and
Luna's compatibility patches. Pure Python source also remains in the runtime.
The dynamically loaded libraries can be replaced with compatible modified builds;
Luna imposes no restriction on reverse engineering to debug those modifications.
See the source archive README for build and replacement locations.

PyTorch bundles NVIDIA CUDA 12.8 and cuDNN redistributable runtime components.
Their upstream EULAs and PyTorch's third-party notices accompany this distribution.
No NVIDIA driver or development toolkit is included.

The public installer contains no voice recordings or voice model packs. Users
choose official Qwen packs in the voice library; pinned revisions, download sizes,
SHA-256 checksums and Apache-2.0 notices are recorded by the catalogue. Existing
David/XTTS and E-Girl/RVC files are retained locally on upgrade. Their recordings
and voice weights are not redistributed by this release.

The former installed runtime also contained unrelated document-generation tools.
Those tools, PyAV/FFmpeg, Praat, demo interfaces and package installation utilities
are excluded from this public build. RVC reads Luna's generated WAV files with
SoundFile. Exact source patches are in `packaging/runtime-patches`.

Sources and release assets:
https://github.com/George-Nizor/Luna/releases/tag/v0.4.1
