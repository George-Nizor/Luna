# Voice catalog and generation library

## Model acquisition

`app/voice_packs.json` records four official Qwen model packs with immutable Hugging Face revisions,
exact file sizes, SHA-256 hashes for LFS weights, and Git blob hashes for configuration/text files.
Only entries in this manifest can be downloaded through the API. It does not download Python code
or enable remote-code execution.

`GET /api/models` returns packs, speaker capabilities, selections, progress, free disk space, and
installation state. `POST /api/voices/selection` saves visible speakers. `POST /api/models/download`
starts one background download; `POST /api/models/download/pause` pauses it. Partial files survive
restarts, so Resume can continue them. Install is an atomic rename after complete verification.
`DELETE /api/models/{pack_id}` removes a Luna-managed pack after unloading the worker.

Existing bundled and local cached Qwen Base checkpoints remain usable. Luna does not remove bundled
assets through the pack manager. Legacy David/E-Girl assets are retained when present, but are not
included in the new official acquisition catalog.

Fast and High resolve to different model repositories. The stored API value `best` retains backward
compatibility while the interface calls it High. David's single XTTS route is called Original.
E-Girl's worker identity includes the source pack, so installing a new source invalidates a worker
using older weights. The worker records the actual source model and available revision.

## Input and output tracking

`GET /api/generation-policy` is the shared source of textbox and backend limits. Request length is
counted in UTF-16 units to agree with the browser's maxlength enforcement. Qwen uses conservative quality-specific segment limits and explicit decoder sampling; temperature is editable and saved for reuse. Segment limits account
for engine, language, and audio-token budget. New generations save original text, actual chosen
seed, parameters, model provenance, elapsed time, duration, sample rate, and bytes.

A codec-budget exhaustion error leaves no completed generation in history. Every text chunk remains
in order, including long sentences containing comma-delimited clauses.

History retention is unlimited by default (`OUTPUT_HISTORY_LIMIT=0`). A positive explicit setting
retains the previous administrator-controlled retention behavior. The desktop uses unlimited
retention. `OUTPUT_HISTORY_DIRECTORIES` is an absolute-path JSON list used to remember previous
output folders; new generations still go to `OUTPUT_DIRECTORY`.

`GET /api/outputs` supports search, quality/voice filters, newest/oldest sorting, and offset/limit
pagination. `GET /api/outputs/{id}` returns details. Audio and metadata exports remain authenticated.
Missing external audio files are shown as missing, while their saved text and metadata remain usable.
Older metadata loads with optional-field defaults; original text is never fabricated.

The Electron bridge accepts output UUIDs for export/reveal, resolves them inside registered output
folders, and rejects traversal and symlinks. Export uses the native Save As dialog; reveal selects
the generated WAV in Explorer. Reuse restores editor parameters without immediately spending GPU time. Playback is released
before deletion. If another app locks the WAV, metadata remains available and the UI reports a
retryable error.

## Validation

Portable Python tests cover model routing, limits, complete chunk preservation, persistent voice
choices, output metadata/search/pagination, old metadata, unlimited retention, previous folders,
download resumption/corruption/cancellation, and storage path safety. Node tests cover desktop file
resolution and packaging without preinstalled weights.

Run `npm test` on Windows. The Python checks can also run with `python -m pytest -q` on Linux;
the Windows release-splitter test is platform-specific. On 2026-10-02, the 0.4.0 package passed all
44 Python checks on Windows (43 plus one platform skip on Linux), two Node desktop checks, and the
Instrumenta suite (232 passed, one Windows symlink-privilege skip).

Headless Edge source checks covered speaker selection, actual quality routing, oversized paste
rejection, history search/reuse, and desktop/mobile layout. Native packaged-app checks used an
isolated Windows data folder and the bundled Python runtime, with no developer Python on PATH.
They verified first launch with no models, checksum-preserving all 37 legacy asset files, official
pack availability, audio playback, WAV export, reveal-path resolution, parameter reuse, and deletion
of the playing output. Save As and Explorer were stubbed at the native dialog/shell boundary; file
export and IPC path checks still ran. No renderer errors were reported.

Five packaged GPU samples on an RTX 4080 SUPER exercised David Original, Ryan Fast/High, and E-Girl
Fast/High. Ryan Fast rendered 983 characters across ten segments into 78.66 seconds of audio. Local
Whisper transcription confirmed the closing sentence in all five recordings. These samples validate
the exercised paths; they do not establish pronunciation or naturalness for every text/language.
Generated samples, validation reports, and model downloads are kept outside Git.

The local 0.3.0-to-0.4.0 installer upgrade completed successfully. Its preservation hook copied and
verified all 37 legacy asset files before uninstall. The installed 0.4.0 executable started with its
own runtime and persistent data root; all eleven voices and both acquired CustomVoice packs were
available. Instrumenta's real Windows probe and discovery reported `READY`, version `0.4.0`.
There were no pre-existing settings/profile/output files in this installation to migrate; legacy
metadata/output retention is covered by the storage tests rather than that empty baseline.
