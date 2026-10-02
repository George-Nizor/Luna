; Preserve the old offline bundle before electron-builder invokes its uninstaller.
; Failure stops the update while the existing installation is still intact.
!ifndef BUILD_UNINSTALLER
Var LunaOldInstall
Var LunaUserData
!macro customInit
  ReadRegStr $LunaOldInstall HKCU "${INSTALL_REGISTRY_KEY}" "InstallLocation"
  ${If} $LunaOldInstall != ""
  ${AndIf} ${FileExists} "$LunaOldInstall\resources\model-data\*.*"
    IfFileExists "$LunaOldInstall\resources\python\python.exe" 0 luna_preserve_failed
    InitPluginsDir
    File /oname=$PLUGINSDIR\preserve_legacy.py "${BUILD_RESOURCES_DIR}\preserve_legacy.py"
    ReadEnvStr $LunaUserData "APPDATA"
    nsExec::ExecToLog '"$LunaOldInstall\resources\python\python.exe" -I "$PLUGINSDIR\preserve_legacy.py" --resources "$LunaOldInstall\resources" --destination "$LunaUserData\luna\data\legacy"'
    Pop $0
    ${If} $0 != "0"
      Goto luna_preserve_failed
    ${EndIf}
    Goto luna_preserve_done
    luna_preserve_failed:
      MessageBox MB_OK|MB_ICONSTOP "Luna could not preserve the existing voice models. The update has stopped before removing your current installation. Check free disk space and permissions, then retry."
      Abort
    luna_preserve_done:
  ${EndIf}
!macroend

!endif
