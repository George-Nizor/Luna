# Brand v2 in Luna

Aligned 2026-10-06 against Instrumenta `brand/` at commit `87f846b` (`brand/ALIGNMENT.md`). Luna was
the last product in the suite to be aligned, and the largest visual change: its deliberate 1-bit,
black-and-white terminal look is replaced entirely. That look (icon and stylesheet) stays archived in
Instrumenta's `brand/archive/v1/luna/` in case it is ever wanted back.

Instrumenta is the source; nothing copied here is edited by hand. To refresh, regenerate in
Instrumenta (`uv run brand/scripts/build-brand.py`) and copy again.

## Copied

| From `Instrumenta/brand/` | To | Used for |
| --- | --- | --- |
| `fonts/*.woff2`, `fonts.css`, `OFL-*.txt` | `app/static/brand/fonts/` | Fraunces, Commissioner, Spline Sans Mono, served by the backend from `/static`; nothing loads from a CDN |
| `icons/instrumenta-icons.{js,css}` | `app/static/brand/` | `InstrumentaIcons.render("luna")` draws the crescent in the top bar. It moves (`ii-play`) while Luna loads, generates or plays, and on hover of the name; `prefers-reduced-motion` stops it |
| `icons/svg/luna{,-24,-16}.svg`, `icons/png/luna-{32,64,256}.png` | `app/static/brand/` | favicon (SVG, PNG fallback) and the mark's no-script fallback |
| `icons/svg/luna*.svg`, `icons/png/luna-*.png`, `icons/ico/luna.ico`, `artwork/luna-app-art.png` | `assets/brand/` | reference set and launcher art; `instrumenta/product.json` `assets.mark` points at the app art |
| `icons/ico/luna.ico`, `icons/png/luna-512.png` | `assets/luna-icon.ico`, `assets/luna-icon.png` | **Same paths as before**: the `Luna.exe` icon (`win.icon`), the NSIS installer and uninstaller icons, the window icon in `electron/main.cjs`, `build_installer.ps1`'s payload check and `package_instrumenta.ps1`'s copy all read these files unchanged. Only the art inside changed (ICO 16 to 256, each size drawn at that size) |
| `icons/svg/luna-animated.svg` | `docs/brand/` | README only (it carries an inline style) |
| `tokens.json` "luna" block and `family` | `app/static/styles.css` `:root` | accent `#73A6C4`, secondary `#A4D9F9` (`--accent-tint`), deep `#20536E`, ink `#041824`, surface `#052231` (banner only) |

Removed: `app/static/luna-icon.png` and `assets/luna-icon-source.png` (the v1 mark).

`docs/images/luna-banner.png` (1600x500) is rendered by `scripts/brand_banner.cjs` from the vendored
files: the luna surface field with the accent at the edges, the name in Fraunces, the crescent from
`InstrumentaIcons.render`, and the one-line description. The README screenshots are taken with
`scripts/ui_screenshots.cjs` against a fake-engine backend.

## Surfaces and themes

Opaque objects with a 2px ink outline and a hard extrusion down and to the right (`--obj-border`,
`--obj-shadow`), flat fills, no glass, glow, gradient, scanlines or ambient motion. Dark is the default
and sits on the family neutrals (`#0d0c0a`, `#141210`, `#1d1a17`, `#352f29`); light is derived from
them (`#f4f1ec` ground, white panels, `#fbf9f6` wells). Every colour is a token on `:root`, written
with `light-dark()`. The page follows the system until someone picks System, Light or Dark in the
top-bar toggle; `static/theme.js` applies the saved choice (`localStorage` `luna.theme`) before first
paint. The Electron window's background follows the system theme so it never flashes black.

Luna's accent is deliberately low in chroma (OKLCH chroma 0.07 against the suite's 0.155), so it is
never louder than the rest of the suite. The interface keeps that: one accent, used for the primary
action, selection, focus, progress and the play buttons; everything else is neutral.

## Roles

- Accent `#73A6C4`: Generate, the play buttons, Download, the selected voice and option, the theme
  toggle, the progress bar. As text, icon or focus ring it is `--accent-text`: the accent on dark,
  deep `#20536E` on light (6.6:1 on dark panels, 8.3:1 on white). Primary buttons are the accent with
  ink `#041824` text (6.9:1) and a deep extrusion. Selected rows use a quiet wash (`--accent-soft`),
  never a large fill behind long text.
- Fraunces (`"SOFT" 100, "WONK" 1`, 660 to 680): the wordmark, dialog titles, "Sound history", and the
  stopped-application headline. Nothing else.
- Commissioner (`"FLAR" 40`): everything operated, now in sentence case (the 1-bit look was all caps).
  The `font` shorthand resets `font-variation-settings`, so the axes come from one property (`--fvs`)
  applied with `!important`; Fraunces elements override it.
- Spline Sans Mono: the character counter, timecodes, sizes, seed and temperature fields, generation
  details (model, sample rate, output ID), the history count, the output folder path, the free-space
  line and the download progress.

## Interface icons

`app/static/brand/luna-icons.js` and `luna-icons.css` are Luna's own set, drawn in the suite style
with the suite's renderer (as Discere's `discere-icons.ts` and Forge3D's `forge-icons.mjs`): a flat
object on a 48 grid with an ink outline and a stepped extrusion, three tiers (full, 24, 16). It is a
classic script exposing `window.LunaIcons` (and `module.exports` for tests), because Luna's page has no
bundler. Output is presentation attributes and classes only. In markup, `<i data-icon="name">` is
replaced on load (`LunaIcons.hydrate`); generated rows call `icon(name, size)` in `app.js`.

| Icon | Where | Hue |
| --- | --- | --- |
| `voice` | Generate (bars pulse while generating), Voice section, voice packs | lunar |
| `cassette` | Voices button, voice library title, empty history | lunar |
| `wavfile`, `metadata` | Export WAV, Metadata | lunar |
| `folder`, `reuse` | Show in folder, Reuse text | lunar |
| `download` | Download a pack | lunar |
| `gear` (turns on hover), `sliders` | Settings, Generation parameters | lunar |
| `mic`, `profile` | Voice profile section and dialog, New profile, cloning packs | lunar |
| `clock`, `chip` | Sound history, Worker | lunar |
| `trash` (lid lifts on hover), `power` | Delete, Remove, Shut down | rose |
| `done` | Ready, Included locally | green |
| `alert`, `failed` | available, not yet used | gold, rose |
| `play`, `pause`, `close`, `chevronDown`, `search`, `external`, `sun`, `moon`, `monitor` | line utilities in `currentColor` | n/a |

The meaning hues (rose, green, gold) are drawn at Luna's quieter chroma (0.11) so no icon is louder
than the lunar accent. Uninstalled packs show their icon in stone. Icon-only buttons keep their
`aria-label`; the icons are `aria-hidden`. All motion stops under `prefers-reduced-motion`.

## Kept, and why

- **The voice visualiser** (the dithered sphere, rings, radial frequency bars and the central glyph)
  and **the playback waveform**: content that responds to the audio, so their shapes are unchanged.
  Only their colours moved from white and greys to the `--viz-*` tokens (a lunar family per theme),
  so they read on either ground; the visualiser already stops animating under reduced motion.
- Every element ID and data attribute `app.js` relies on, the menus' listbox semantics, dialogs, the
  hidden selects and the backend API: the restyle changes presentation, not behaviour.
- User content stays as the user wrote it: voice names, profile names and transcripts are no longer
  forced into capitals, and transcripts and history text use the readable interface face, not mono.
- The installer, uninstall record, `DisplayVersion`, release manifest template, `appId`, product name,
  executable name and launch paths: untouched (see "Copied" for the icon files that kept their paths).

## Verification

- `pytest` (47 pass, 1 skipped), `ruff check app tests`, `node --check` on every script, and
  `node --test tests-electron/*.test.cjs` (6 pass, including the new icon test), run in WSL.
- The interface was screenshotted in headless Chromium against the real backend with `ENGINE=fake`,
  dark and light: main, latest output, generating, history with details, voice menu, settings, voice
  library, new profile, shut down, keyboard focus and a narrow window. Computed styles confirm the three
  faces and the `FLAR`/`SOFT`/`WONK` axes apply, and that under reduced motion the icon, mark and
  progress animations resolve to `none`.

## Not verified / follow-ups

- No Windows package was built and the real Electron window was not run: `npm run dist` needs the
  multi-gigabyte CUDA runtime payload. The change to packaging is confined to the art inside
  `assets/luna-icon.{ico,png}`, whose paths, sizes and format the branding test now checks.
- The crescent's voice bars are drawn in the brand ink (`#041824`), which almost disappears on dark
  grounds, Luna's own `surface` included (visible in the banner and the dark top bar, where only the
  deep extrusion shows them). That is the glyph in Instrumenta's `instrumenta-icons.js`; a library
  revision could fill the bars in accent and tint like the crescent. Not changed here.
- Audio with real speech was not played through the visualiser; the fake engine's output is near
  silent, so the "playing" state was judged from the idle and generating states.
