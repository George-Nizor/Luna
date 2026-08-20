[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [string]$InputPath,
  [Parameter(Mandatory)]
  [string]$InstallerPath,
  [string]$OutputDirectory = "",
  [ValidateRange(1048576, 2147483647)]
  [long]$ChunkSizeBytes = 1992294400
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReleaseRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "release"))
$Source = Get-Item -LiteralPath $InputPath
$Installer = Get-Item -LiteralPath $InstallerPath
if ($Source.PSIsContainer -or $Installer.PSIsContainer) {
  throw "InputPath and InstallerPath must both be files."
}
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $ReleaseRoot "publish\v0.3.0"
}
$OutputFullPath = [IO.Path]::GetFullPath($OutputDirectory)
$ReleaseBoundary = $ReleaseRoot.TrimEnd('\') + '\'
if (-not $OutputFullPath.StartsWith($ReleaseBoundary, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Release assets must be written inside $ReleaseRoot."
}
if (Test-Path -LiteralPath $OutputFullPath) {
  throw "Refusing to replace an existing release directory: $OutputFullPath"
}

$Staging = "$OutputFullPath.staging-$PID"
if (Test-Path -LiteralPath $Staging) {
  throw "Staging directory already exists: $Staging"
}
New-Item -ItemType Directory -Path $Staging | Out-Null

function Get-Sha256([string]$Path) {
  $Stream = [IO.File]::OpenRead($Path)
  $Hasher = [Security.Cryptography.SHA256]::Create()
  try {
    $HashBytes = $Hasher.ComputeHash($Stream)
    return ([BitConverter]::ToString($HashBytes)).Replace("-", "").ToLowerInvariant()
  } finally {
    $Hasher.Dispose()
    $Stream.Dispose()
  }
}

try {
  $PublishedInstaller = Join-Path $Staging $Installer.Name
  Copy-Item -LiteralPath $Installer.FullName -Destination $PublishedInstaller

  $Chunks = @()
  $InputStream = [IO.File]::OpenRead($Source.FullName)
  try {
    $Buffer = New-Object byte[] (8MB)
    $Part = 1
    while ($InputStream.Position -lt $InputStream.Length) {
      $ChunkName = "{0}.part{1:D3}" -f $Source.Name, $Part
      $ChunkPath = Join-Path $Staging $ChunkName
      $ChunkStream = [IO.File]::Open($ChunkPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
      try {
        $Written = 0L
        while ($Written -lt $ChunkSizeBytes -and $InputStream.Position -lt $InputStream.Length) {
          $Requested = [Math]::Min($Buffer.Length, $ChunkSizeBytes - $Written)
          $Read = $InputStream.Read($Buffer, 0, [int]$Requested)
          if ($Read -le 0) { break }
          $ChunkStream.Write($Buffer, 0, $Read)
          $Written += $Read
        }
      } finally {
        $ChunkStream.Dispose()
      }
      $Chunk = Get-Item -LiteralPath $ChunkPath
      $Chunks += [ordered]@{
        asset = $Chunk.Name
        size = $Chunk.Length
        sha256 = Get-Sha256 $Chunk.FullName
      }
      $Part += 1
    }
  } finally {
    $InputStream.Dispose()
  }

  $Manifest = [ordered]@{
    schemaVersion = 1
    product = "luna"
    version = "0.3.0"
    platform = "windows-x64"
    minimumInstrumentaVersion = "0.8.0"
    installStrategy = "installed-desktop"
    installer = [ordered]@{
      asset = $Installer.Name
      size = $Installer.Length
      sha256 = Get-Sha256 $Installer.FullName
    }
    payload = [ordered]@{
      assembledAsset = $Source.Name
      size = $Source.Length
      sha256 = Get-Sha256 $Source.FullName
      chunks = $Chunks
    }
  }
  $ManifestPath = Join-Path $Staging "instrumenta-release.json"
  [IO.File]::WriteAllText(
    $ManifestPath,
    ($Manifest | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
  )
  New-Item -ItemType Directory -Path (Split-Path -Parent $OutputFullPath) -Force | Out-Null
  Move-Item -LiteralPath $Staging -Destination $OutputFullPath
  Write-Host "Prepared $($Chunks.Count) payload chunks and manifest in $OutputFullPath"
} catch {
  if (Test-Path -LiteralPath $Staging) {
    Remove-Item -LiteralPath $Staging -Recurse -Force
  }
  throw
}
