# Luna identity and data locations

## Product identity

Luna 0.3.0 is a cleanly reinstalled Windows x64 application. Its stable identity is:

- Product, shortcut, installer, executable, and window title: `Luna`
- Windows executable: `Luna.exe`
- Application ID: `com.instrumenta.luna`
- npm and Python project name: `luna`
- Windows uninstall display name: `Luna`

“Luna Voice Studio” is an obsolete product identity. The 0.3.0 installer does not migrate its
settings, caches, shortcuts, registry entry, or generated output.

## User-owned locations

- Settings, profiles, backend state, and logs: `%APPDATA%\Luna`
- Default generated output: `%USERPROFILE%\Documents\Luna`
- Installed executable: the per-user directory selected by the Luna installer

Uninstall removes the application and its registered shortcuts. It does not silently remove
`%APPDATA%\Luna` or generated audio. A deliberate cleanup can remove those only after the user has
confirmed the content is disposable or backed up.

## Clean reinstall checklist

1. Back up any old recordings that must be retained.
2. Uninstall “Luna Voice Studio” through its registered Windows uninstaller.
3. Confirm the obsolete executable, shortcuts, and uninstall entry are gone.
4. Install Luna 0.3.0 from the matching verified installer and payload.
5. Confirm the title, executable, shortcuts, uninstall display name, App ID, settings root, and
   output root use only the new identity.
6. Remove old caches and disposable outputs only after the new installation generates and plays a
   test WAV successfully.

No automatic migration is intentional: it prevents old settings and model caches from becoming
implicit dependencies of the renamed product.