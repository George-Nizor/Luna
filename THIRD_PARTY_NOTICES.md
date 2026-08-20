# Third-party notices

Luna is MIT-licensed, but its packaged runtime includes third-party software and
model assets under their own terms. Release builders must preserve the notices
shipped by Electron, Python, PyTorch, Qwen3-TTS, XTTS, RVC, FFmpeg, and their
transitive dependencies.

The source and packaged dependency groups include permissively licensed Electron,
FastAPI, Uvicorn, Pydantic, Jinja, python-multipart, SoundFile, NumPy, psutil,
PyTorch, and Qwen components, plus Coqui TTS under MPL-2.0. Exact transitive
licenses from the locked release environment must accompany the installer.
FFmpeg redistribution depends on the actual packaged build configuration and
must be audited as LGPL/GPL as applicable.

The file `assets/egirl-source-reference.wav` is intentionally ignored. A release
builder must supply a reference recording they have the right to redistribute.
No model weights, downloaded archives, generated voices, or private reference
recordings belong in Git history. The David reference recording, E-Girl model,
Qwen weights, XTTS weights, and RVC base assets must each have documented
redistribution permission before their payload is published.
