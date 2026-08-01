# Eli OS survivable-instance bootstrap.
# On any Windows machine with OneDrive signed in + Python 3.9+ installed:
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 [-Serve]
# Hydrates a local runtime from the OneDrive durable core and (optionally)
# starts the gateway on 127.0.0.1:8484. Idempotent — safe to re-run.

param(
    [switch]$Serve,          # start the gateway after hydrating
    [string]$Core = "",      # override durable-core path
    [string]$Runtime = ""    # override local-runtime path
)

$ErrorActionPreference = "Stop"

# 1. Locate the durable core inside OneDrive.
if (-not $Core) {
    $od = $env:OneDrive
    if (-not $od) { $od = $env:OneDriveConsumer }
    if (-not $od) { $od = $env:OneDriveCommercial }
    if (-not $od) { throw "OneDrive not signed in and -Core not given." }
    $Core = Join-Path $od "DominionLabs\eli-instance"
}
if (-not (Test-Path $Core)) { New-Item -ItemType Directory -Path $Core -Force | Out-Null }
Write-Host "core:    $Core"

# 2. Local runtime — hot files live here, never in the synced folder.
if (-not $Runtime) { $Runtime = Join-Path $env:LOCALAPPDATA "EliOS" }
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
Write-Host "runtime: $Runtime"

# 3. Get the repo: prefer the bundle in the core (survives GitHub outages and
#    auth loss); fall back to GitHub if no bundle exists yet.
$RepoDir = Join-Path $Runtime "repo"
$Bundle  = Join-Path $Core "repo\eli.bundle"
if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    if (Test-Path $Bundle) {
        git clone $Bundle $RepoDir
    } else {
        git clone https://github.com/thenot-lab/thenot-lab.github.io $RepoDir
    }
} elseif (Test-Path $Bundle) {
    git -C $RepoDir fetch $Bundle | Out-Null
}
Write-Host "repo:    $RepoDir"

# 4. Restore newest state snapshots into the runtime.
$Snapshot = Join-Path $RepoDir "eli-os\instance\snapshot.py"
$env:ELI_CORE = $Core
$env:ELI_RUNTIME = $Runtime
python $Snapshot restore

# 5. Wire the gateway to the runtime (hot telemetry stays local; it reaches
#    the core only via `snapshot.py snapshot`).
$env:ELI_TELEMETRY = Join-Path $Runtime "telemetry.jsonl"

if ($Serve) {
    Set-Location (Join-Path $RepoDir "eli-os\gateway")
    python gateway.py serve --port 8484
} else {
    Write-Host "hydrated. Start with: python `"$RepoDir\eli-os\gateway\gateway.py`" serve --port 8484"
    Write-Host "snapshot back to core with: python `"$Snapshot`" snapshot"
}
