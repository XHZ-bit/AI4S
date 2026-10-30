param(
    [ValidateSet('Docker','Local')][string]$Mode = 'Docker',
    [string]$DataDir,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Check,
    [switch]$Offline,
    [switch]$AllowAnonymous
)
$ErrorActionPreference = 'Stop'
$atlasRoot = $PSScriptRoot
$atlasEnvironmentNames = @('DASHSCOPE_API_KEY','RESEARCH_MODEL_ENABLED','OFFLINE_MODE','ACCESS_MODE','REQUIRE_LOGIN','DATA_DIR','ATLAS_ENV_FILE','RUNTIME_MODE','RUNTIME_ID','ATLAS_API_TARGET')
$atlasEnvironmentSaved = @{}
foreach ($atlasEnvironmentName in $atlasEnvironmentNames) {
    $atlasEnvironmentSaved[$atlasEnvironmentName] = [Environment]::GetEnvironmentVariable($atlasEnvironmentName, 'Process')
}
try {
if ($env:ACCESS_MODE -eq 'multiuser') { throw 'start.ps1 manages single-user local profiles only. Use docker-compose.multiuser.yml or docs/multiuser-trial.md for controlled multi-user deployment.' }
$env:ACCESS_MODE = 'local'
$env:REQUIRE_LOGIN = if ($AllowAnonymous) { 'false' } else { 'true' }
if ($BackendPort -lt 1 -or $BackendPort -gt 65535 -or $FrontendPort -lt 1 -or $FrontendPort -gt 65535 -or $FrontendPort -eq $BackendPort) { throw 'Invalid service ports' }
if ($Mode -eq 'Docker') {
    if ($DataDir -or $BackendPort -ne 8000 -or $FrontendPort -ne 5173) { throw 'Docker uses existing named volumes and fixed ports; local DataDir/ports require -Mode Local' }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is not installed. Use -Mode Local for local data.' }
    if ($Check) { Write-Output 'Docker mode: existing Compose volumes; no model key required'; exit 0 }
    $atlasKey = [Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY','Process')
    if ([string]::IsNullOrWhiteSpace($atlasKey)) { $atlasKey = [Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY','User') }
    if ($Offline) { $env:DASHSCOPE_API_KEY = ''; $env:RESEARCH_MODEL_ENABLED = 'false'; $env:OFFLINE_MODE = 'true' } elseif ($atlasKey) { $env:DASHSCOPE_API_KEY = $atlasKey }
    Push-Location $atlasRoot
    try {
        docker compose up -d --build
        if ($LASTEXITCODE -ne 0) { throw 'Docker startup failed. No automatic data-mode switch was made. Use -Mode Local with the intended DataDir.' }
    } finally { Pop-Location }
    Write-Output 'PaperStride: http://127.0.0.1:5173/ (Docker volume data)'
    exit 0
}
if (-not $DataDir) { $DataDir = Join-Path $atlasRoot 'backend\data' }
$atlasData = [IO.Path]::GetFullPath($DataDir)
$atlasPython = Join-Path $atlasRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $atlasPython)) { throw 'Project Python is missing. Run .\scripts\setup-dependencies.ps1 first; global Python is not used for local services.' }
$atlasNode = (Get-Command node -ErrorAction Stop).Source
$atlasVite = Join-Path $atlasRoot 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $atlasVite)) { throw 'Frontend dependencies missing. Run npm ci in frontend.' }
& $atlasPython -c 'import fastapi, uvicorn, pydantic_settings, neo4j, pymupdf, multipart'
if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies missing. Run .\scripts\setup-dependencies.ps1 -SkipFrontend.' }
if ($Check) { Write-Output "Local mode ready; data: $atlasData; API: $BackendPort; frontend: $FrontendPort"; exit 0 }
$atlasApi = "http://127.0.0.1:$BackendPort"
$atlasExisting = $null
try { $atlasExisting = Invoke-RestMethod "$atlasApi/api/system/status" -TimeoutSec 15 } catch {}
if (-not $atlasExisting) {
    try {
        $atlasSession = Invoke-RestMethod "$atlasApi/api/auth/session" -TimeoutSec 6
        if ($atlasSession.require_login) { throw 'A login-protected runtime already uses this port. Stop it before starting a new profile.' }
    } catch { if ($_.Exception.Message -like 'A login-protected runtime*') { throw } }
}
if ($atlasExisting) {
    if ($atlasExisting.data_dir -ne $atlasData -or $atlasExisting.mode -ne 'local') { throw 'API port belongs to a different data profile. Stop that service or choose other ports.' }
    if ($Offline -and ($atlasExisting.services.model.status -ne 'unconfigured' -or $atlasExisting.services.model.research_enabled)) { throw 'Existing runtime has a model configuration. Restart it with -Offline before using the offline profile.' }
    try { $atlasFront = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/api/system/status" -UseBasicParsing -TimeoutSec 15; $atlasFrontInfo = $atlasFront.Content | ConvertFrom-Json } catch { throw 'API is running but frontend is unavailable. Stop the managed runtime and start again.' }
    if ($atlasFrontInfo.pid -ne $atlasExisting.pid) { throw 'Frontend points to a different API. Choose the matching profile.' }
    Write-Output "Already running: http://127.0.0.1:$FrontendPort/ ; data: $atlasData"
    exit 0
}
foreach ($atlasPort in @($BackendPort,$FrontendPort)) {
    $atlasPortProbe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $atlasPort)
    try {
        $atlasPortProbe.ExclusiveAddressUse = $true
        $atlasPortProbe.Start()
    } catch { throw "Port $atlasPort is occupied or unavailable; no existing process was stopped" }
    finally { $atlasPortProbe.Stop() }
}
$atlasRun = Join-Path $atlasRoot ".tmp\run\$BackendPort"
New-Item -ItemType Directory -Force -Path $atlasRun | Out-Null
$atlasIdentity = [guid]::NewGuid().ToString()
Push-Location (Join-Path $atlasRoot 'frontend')
try { & $atlasNode 'scripts/pdf-assets.mjs'; if ($LASTEXITCODE -ne 0) { throw 'PDF reader assets could not be prepared' } } finally { Pop-Location }
$env:DATA_DIR = $atlasData
$env:ATLAS_ENV_FILE = if ($Offline) { Join-Path $atlasRun "$atlasIdentity.no-env" } else { Join-Path $atlasRoot '.env' }
$env:RUNTIME_MODE = 'local'
$env:RUNTIME_ID = $atlasIdentity
$env:ATLAS_API_TARGET = $atlasApi
$atlasKey = [Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY','Process')
if (-not $atlasKey) { $atlasKey = [Environment]::GetEnvironmentVariable('DASHSCOPE_API_KEY','User') }
if ($Offline) { $env:DASHSCOPE_API_KEY = ''; $env:RESEARCH_MODEL_ENABLED = 'false'; $env:OFFLINE_MODE = 'true' } elseif ($atlasKey) { $env:DASHSCOPE_API_KEY = $atlasKey }
$atlasBackend = $null
$atlasFrontend = $null
try {
    $atlasBackend = Start-Process -FilePath $atlasPython -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$BackendPort") -WorkingDirectory (Join-Path $atlasRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $atlasRun 'backend.out.log') -RedirectStandardError (Join-Path $atlasRun 'backend.err.log') -PassThru
    $atlasFrontend = Start-Process -FilePath $atlasNode -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',"$FrontendPort",'--strictPort') -WorkingDirectory (Join-Path $atlasRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $atlasRun 'frontend.out.log') -RedirectStandardError (Join-Path $atlasRun 'frontend.err.log') -PassThru
    $atlasReady = $false
    for ($atlasAttempt=0; $atlasAttempt -lt 40; $atlasAttempt++) {
        if ($atlasBackend.HasExited -or $atlasFrontend.HasExited) { throw 'Service exited. Inspect .tmp/run logs.' }
        try {
            $atlasProbe = Invoke-RestMethod "http://127.0.0.1:$FrontendPort/api/auth/session" -TimeoutSec 15
            $atlasHealth = Invoke-RestMethod "http://127.0.0.1:$BackendPort/health" -TimeoutSec 15
            if ($atlasProbe.runtime_id -eq $atlasIdentity -and $atlasHealth.status -eq 'ok') { $atlasReady=$true; break }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $atlasReady) { throw 'Service health check timed out. Inspect .tmp/run logs.' }
    # The Windows venv launcher may spawn a different Python PID. Track the
    # verified HTTP server itself so stop/restart cannot leave it behind.
    $atlasBackendServer = Get-Process -Id $atlasProbe.pid -ErrorAction Stop
    @{runtime_id=$atlasIdentity;backend_pid=$atlasBackendServer.Id;frontend_pid=$atlasFrontend.Id;backend_started_utc=$atlasBackendServer.StartTime.ToUniversalTime().ToString('o');frontend_started_utc=$atlasFrontend.StartTime.ToUniversalTime().ToString('o');data_dir=$atlasData;backend_port=$BackendPort;frontend_port=$FrontendPort;mode='Local';offline=[bool]$Offline} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $atlasRun 'runtime.json') -Encoding utf8
} catch {
    foreach ($atlasProcess in @($atlasBackend,$atlasFrontend)) { if ($atlasProcess -and -not $atlasProcess.HasExited) { Stop-Process -Id $atlasProcess.Id -ErrorAction SilentlyContinue } }
    throw
}
Write-Output "PaperStride: http://127.0.0.1:$FrontendPort/ ; data: $atlasData ; state: ready"
} finally {
    # The children keep their inherited profile; the caller keeps its own one.
    foreach ($atlasEnvironmentName in $atlasEnvironmentNames) {
        if ($null -eq $atlasEnvironmentSaved[$atlasEnvironmentName]) {
            Remove-Item -LiteralPath "Env:$atlasEnvironmentName" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($atlasEnvironmentName, $atlasEnvironmentSaved[$atlasEnvironmentName], 'Process')
        }
    }
}
