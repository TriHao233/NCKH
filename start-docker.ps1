param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Continue"
$services = @("backend", "frontend", "mongodb", "worker")
$composeArgs = @("compose", "up", "-d", "--quiet-build")
if (-not $NoBuild) {
    $composeArgs += "--build"
}

$composeOutput = & docker @composeArgs 2>&1
$composeExitCode = $LASTEXITCODE
if ($composeExitCode -ne 0) {
    Write-Host "DOCKER BUILD FAILED"
    $composeOutput | Write-Host
    exit $composeExitCode
}

$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 2
    $runningServices = @(& docker compose ps --status running --services 2>$null)
    $allRunning = @($services | Where-Object { $_ -notin $runningServices }).Count -eq 0
} while (-not $allRunning -and (Get-Date) -lt $deadline)

if (-not $allRunning) {
    Write-Host "DOCKER START FAILED"
    & docker compose ps
    & docker compose logs --tail 60
    exit 1
}

Write-Host ""
Write-Host 'DOCKER BUILDING SUCCESSFUL, FOLLOW "LOCALHOST" TO OPEN WEBSITE'
Write-Host "http://localhost"
