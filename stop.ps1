param([ValidateSet('Local','Docker')][string]$Mode='Local',[int]$BackendPort=8000)
$ErrorActionPreference='Stop'
if ($Mode -eq 'Docker') {
    Push-Location $PSScriptRoot
    try { docker compose stop; if ($LASTEXITCODE -ne 0) { throw 'Compose stop failed' } } finally { Pop-Location }
    exit 0
}
$atlasMetadata=Join-Path $PSScriptRoot ".tmp\run\$BackendPort\runtime.json"
if (-not (Test-Path -LiteralPath $atlasMetadata)) { Write-Output 'No managed local runtime'; exit 0 }
$atlasRun=Get-Content -LiteralPath $atlasMetadata -Raw | ConvertFrom-Json
$atlasProbe=$null
try { $atlasProbe=Invoke-RestMethod "http://127.0.0.1:$($atlasRun.backend_port)/api/system/status" -TimeoutSec 6 } catch {}
if ($atlasProbe -and $atlasProbe.runtime_id -ne $atlasRun.runtime_id) { throw 'API identity changed; refusing to stop another runtime' }
foreach ($atlasRole in @('backend','frontend')) {
    $atlasPid=if ($atlasRole -eq 'backend') { $atlasRun.backend_pid } else { $atlasRun.frontend_pid }
    $atlasProcess=Get-Process -Id $atlasPid -ErrorAction SilentlyContinue
    if ($atlasProcess) {
        $atlasStarted=if ($atlasRole -eq 'backend') { $atlasRun.backend_started_utc } else { $atlasRun.frontend_started_utc }
        if (-not $atlasStarted) { throw 'Legacy runtime metadata lacks process creation time; refusing to stop an unverified process' }
        # PowerShell 7 may deserialize ISO timestamps directly to DateTime.
        # Casting preserves its fractional seconds; Parse(object) stringifies
        # that value first and can lose the precision used for PID checks.
        $atlasStartedUtc=([datetime]$atlasStarted).ToUniversalTime()
        if ([Math]::Abs(($atlasProcess.StartTime.ToUniversalTime() - $atlasStartedUtc).TotalMilliseconds) -gt 1) { throw "Process identity changed for $atlasRole; refusing to stop it" }
        Stop-Process -InputObject $atlasProcess -Force
        if (-not $atlasProcess.WaitForExit(15000)) { throw "Timed out stopping verified $atlasRole process; runtime metadata retained" }
    }
}
$atlasAfterStop=$null
try { $atlasAfterStop=Invoke-RestMethod "http://127.0.0.1:$($atlasRun.backend_port)/api/system/status" -TimeoutSec 2 } catch {}
if ($atlasAfterStop -and $atlasAfterStop.runtime_id -eq $atlasRun.runtime_id) {
    throw 'Managed API still responds after stop; runtime metadata retained for recovery'
}
Remove-Item -LiteralPath $atlasMetadata
Write-Output 'Local services stopped; saved data retained'
