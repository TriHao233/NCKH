[CmdletBinding()]
param(
    [switch]$Build,
    [string]$DockerDiskDirectory = "$env:LOCALAPPDATA\Docker\wsl\disk",
    [int]$MinimumFreeGB = 35
)

$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$storageRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($DockerDiskDirectory))
$storageDrive = [IO.DriveInfo]::new($storageRoot)
if ($MinimumFreeGB -lt 10) { throw 'MinimumFreeGB must be at least 10 GiB.' }
if ($storageDrive.AvailableFreeSpace -lt ($MinimumFreeGB * 1GB)) {
    throw "$storageRoot needs at least $MinimumFreeGB GiB free for Docker images and cache."
}
$composeArgs = @('compose', '-f', (Join-Path $repoPath 'docker-compose.yml'))
& docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose validation failed.' }
Write-Host "Storage check passed on $storageRoot. No service has been restarted."
if (-not $Build) { Write-Host 'Check only. Use -Build when ready to build the images.'; return }

# Only builds two images. Worker uses the same backend image; no up/restart/down/prune.
& docker @composeArgs build docling backend
if ($LASTEXITCODE -ne 0) { throw 'Build failed. Existing running services were not replaced.' }
Write-Host 'Images built. Existing services remain running; activation is a separate step.'
