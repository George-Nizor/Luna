# Third-party notices — Luna 0.6.0

Luna application code is MIT ([LICENSE](LICENSE)). The installer also carries these components, each
under its own licence:

- **Electron 43.4.0 and Chromium.** MIT for Electron; Chromium's notices are installed beside
  `Luna.exe` as `LICENSE.electron.txt` and `LICENSES.chromium.html`.
- **uv 0.12.23** by Astral Software Inc., unmodified, MIT OR Apache-2.0. Both licence texts are in
  `resources\runtime\uv`. Notices for the Rust crates compiled into uv are in its source:
  https://github.com/astral-sh/uv/tree/0.12.23
- **fairseq 0.12.2** (MIT, Facebook, Inc. and its affiliates), **antlr4-python3-runtime 4.8**
  (BSD-3-Clause, The ANTLR Project) and **sox 1.5.0** (BSD-3-Clause, Rachel Bittner and contributors),
  as wheels built from their unmodified PyPI source archives in `resources\runtime\wheels`. The
  fairseq and sox wheels carry their licences in `.dist-info`; the ANTLR runtime's source archive
  ships none, so its licence (from ANTLR's 4.8 repository) is reproduced at the end of this file.
- **Fraunces, Commissioner and Spline Sans Mono**, SIL Open Font License 1.1, with their licence
  texts in `app/static/brand/fonts`.

Luna does not redistribute Python, PyTorch, NVIDIA's CUDA libraries or other Python packages. On first
start each installation downloads CPython 3.12 (python-build-standalone, through uv) and the wheels
listed in `resources\runtime\runtime-lock.json` from the Python Package Index and PyTorch's download
server, under their publishers' licences, and checks every file against the SHA-256 in that list.
After installing them Luna makes five small source changes on the user's machine (listed in
`resources\runtime\apply_patches.py`); the changed files are never redistributed.

The release contains no voice recordings or voice model packs. Users choose official Qwen packs in
the voice library; pinned revisions, download sizes, SHA-256 checksums and Apache-2.0 notices are
recorded by the catalogue. Existing David/XTTS and E-Girl/RVC files are retained locally on upgrade
and are not redistributed.

Sources and release assets: https://github.com/George-Nizor/Luna/releases/tag/v0.6.0

## ANTLR 4.8 runtime licence

```text
[The "BSD 3-clause license"]
Copyright (c) 2012-2017 The ANTLR Project. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:

 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.
 3. Neither the name of the copyright holder nor the names of its contributors
    may be used to endorse or promote products derived from this software
    without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
