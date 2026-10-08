# Run from an interactive PowerShell session owned by the Docker Desktop user.
# Preserves stale socket directories; never deletes images, containers or WSL data.
$ErrorActionPreference = 'Stop'

try {
    if (Get-Process 'Docker Desktop', 'com.docker.backend' -ErrorAction SilentlyContinue) {
        throw 'Quit Docker Desktop from its tray menu before running this script.'
    }
    if (-not (Get-CimInstance Win32_ComputerSystem).HypervisorPresent) {
        throw 'Windows Hypervisor is off. Switch to Docker mode and reboot first.'
    }
    $localRoot = [IO.Path]::GetFullPath($env:LOCALAPPDATA)
    $targets = @(
        @{ Relative = 'docker-secrets-engine'; Allowed = @('engine.sock') },
        @{ Relative = 'Docker\run'; Allowed = @('dockerInference', 'dockerEthernetVfkit', 'userAnalyticsOtlpHttp.sock') }
    )
    # Validate both directories before making any changes.
    foreach ($target in $targets) {
        $target.Path = [IO.Path]::GetFullPath((Join-Path $localRoot $target.Relative))
        if (-not $target.Path.StartsWith($localRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unexpected runtime directory path.'
        }
        if (Test-Path -LiteralPath $target.Path) {
            $entries = @(Get-ChildItem -LiteralPath $target.Path -Force)
            foreach ($entry in $entries) {
                if ($entry.PSIsContainer -or $entry.Name -notin $target.Allowed -or $entry.Length -ne 0) {
                    throw "Unexpected contents in $($target.Path); no repair performed."
                }
            }
        }
    }
    foreach ($target in $targets) {
        if (Test-Path -LiteralPath $target.Path) {
            $savedName = (Split-Path $target.Path -Leaf) + '.preserved-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
            Rename-Item -LiteralPath $target.Path -NewName $savedName
            Write-Host "Preserved runtime directory: $savedName"
        }
        New-Item -ItemType Directory -Path $target.Path | Out-Null
    }
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $desktop)) { throw "Docker Desktop not found: $desktop" }
    Start-Process -FilePath $desktop -WindowStyle Hidden
    Write-Host 'Docker Desktop launched. After the engine is ready, run:'
    Write-Host '  docker version'
    Write-Host '  docker info --format "{{.OSType}}"'
    Write-Host 'Success requires a Server section and OSType linux. Then retry the platform lab.'
} catch {
    Write-Error "Repair did not complete: $($_.Exception.Message)" -ErrorAction Continue
    Write-Host 'No Docker image/container/WSL data was deleted. If access is denied, run this script from an elevated interactive PowerShell under your usual Windows account.'
    exit 1
}
