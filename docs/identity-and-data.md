# Luna identity and data locations

## Product identity

Luna 0.6.0 is a Windows x64 application. Its stable identity is:

- Product, shortcut, installer, executable, and window title: `Luna`
- Windows executable: `Luna.exe`
- Application ID: `com.instrumenta.luna`
- npm and Python project name: `luna`
- Windows uninstall display name: `Luna <version>` (older installers may use `Luna`)

“Luna Voice Studio” is an obsolete product identity. The 0.3.0 installer does not migrate its
settings, caches, shortcuts, registry entry, or generated output.

## User-owned locations

- Settings, profiles, backend state, and logs: `%APPDATA%\Luna`
- Preserved models from older Luna installations: `%APPDATA%\Luna\data\legacy`
- Downloaded optional models: `%APPDATA%\Luna\data\model-packs`
- Default generated output: `%USERPROFILE%\Documents\Luna`
- Installed executable: the per-user directory selected by the Luna installer
- Python runtime (since 0.6.0, set up by Luna on first start): `%LOCALAPPDATA%\Luna\runtime`, with
  one CPython under `python` and one environment named by its lock hash. It holds no user data and is
  rebuilt if removed.

Uninstall removes the application, its registered shortcuts and, from 0.6.0, the Python runtime in
`%LOCALAPPDATA%\Luna\runtime`. It does not silently remove
`%APPDATA%\Luna` or generated audio. A deliberate cleanup can remove those only after the user has
confirmed the content is disposable or backed up.

## Upgrading Luna

The installer preserves bundled voice weights from an existing Luna installation (0.3.0 and 0.4.x
carried them in `resources\model-data`) before invoking its uninstaller. It checks every copy by size and SHA-256 and stops before removal if a
copy fails or an existing preserved file differs. Settings, acquired packs, and generated output
remain in their persistent locations. The old uninstaller removes the previous program folder,
including the Python runtime 0.3.0 and 0.4.x bundled in `resources\python`; 0.6.0 sets up its own on
first start. The uninstall record keeps its key and becomes `Luna 0.6.0`, version 0.6.0, which is what
Instrumenta reads. This is separate from the historical product rename below.

## Historical rename: clean reinstall checklist

1. Back up any old recordings that must be retained.
2. Uninstall “Luna Voice Studio” through its registered Windows uninstaller.
3. Confirm the obsolete executable, shortcuts, and uninstall entry are gone.
4. Install Luna 0.3.0 from the matching verified installer and payload.
5. Confirm the title, executable, shortcuts, uninstall display name, App ID, settings root, and
   output root use only the new identity.
6. Remove old caches and disposable outputs only after the new installation generates and plays a
   test WAV successfully.

The historical rename intentionally did not migrate the retired identity. Updates between Luna
versions preserve the current identity and user data.
