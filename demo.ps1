param(
    [ValidateSet('Prepare','Start','Stop','Restart','Status','Check')][string]$Action = 'Start',
    [string]$DataDir = (Join-Path $PSScriptRoot '.demo\data'),
    [string]$PdfDir = (Join-Path $PSScriptRoot '.tmp\second-demo-sources'),
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Synthetic
)
$ErrorActionPreference = 'Stop'
if ($Synthetic -and -not $PSBoundParameters.ContainsKey('DataDir')) { $DataDir = Join-Path $PSScriptRoot '.demo\synthetic-data' }
$atlasDemoPrepareOptions = @()
if ($Synthetic) { $atlasDemoPrepareOptions += '--synthetic-only' }
$atlasDemoData = [IO.Path]::GetFullPath($DataDir)
$atlasDemoPython = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if ($Action -ne 'Stop' -and -not (Test-Path -LiteralPath $atlasDemoPython)) { throw 'Project Python is missing. Run .\scripts\setup-dependencies.ps1 first; global Python is not used for the demo.' }
$atlasDemoPrepare = Join-Path $PSScriptRoot 'backend\scripts\prepare_demo.py'
$atlasDemoMetadata = Join-Path $PSScriptRoot ".tmp\run\$BackendPort\runtime.json"

function Test-DemoData {
    & $atlasDemoPython $atlasDemoPrepare --data-dir $atlasDemoData --check
    if ($LASTEXITCODE -ne 0) { throw 'Demo validation failed; existing files were kept' }
}

function Test-DemoRuntimeIdentity {
    if (-not (Test-Path -LiteralPath $atlasDemoMetadata)) { return $false }
    $atlasDemoRun = Get-Content -LiteralPath $atlasDemoMetadata -Raw | ConvertFrom-Json
    if ([IO.Path]::GetFullPath($atlasDemoRun.data_dir) -ne $atlasDemoData) {
        throw 'Managed port belongs to another data directory; it was not stopped'
    }
    return $true
}

function Start-DemoRuntime {
    & $atlasDemoPython $atlasDemoPrepare --data-dir $atlasDemoData --pdf-dir $PdfDir @atlasDemoPrepareOptions
    if ($LASTEXITCODE -ne 0) { throw 'Demo preparation failed; no service was started' }
    # Child processes inherit only this temporary demo profile. Even an existing
    # project .env cannot enable a model or connect to a real graph/parser here.
    $atlasDemoManaged = Test-DemoRuntimeIdentity
    $atlasDemoPrevious = $null
    if ($atlasDemoManaged) {
        $atlasDemoPrevious = Get-Content -LiteralPath $atlasDemoMetadata -Raw | ConvertFrom-Json
    }
    try { $atlasDemoLive = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/system/status" -TimeoutSec 6 } catch { $atlasDemoLive = $null }
    if ($atlasDemoLive -and (-not $atlasDemoManaged -or $atlasDemoLive.runtime_id -ne $atlasDemoPrevious.runtime_id -or -not $atlasDemoPrevious.offline -or -not $atlasDemoPrevious.demo_isolated_services)) {
        throw 'Existing Local runtime does not use the managed isolated demo profile. Use demo.ps1 -Action Restart for this managed profile, or stop the other service and choose free ports.'
    }
    $atlasDemoVariables = @('DASHSCOPE_API_KEY','RESEARCH_MODEL_ENABLED','NEO4J_URI','GROBID_BASE_URL','DATA_DIR','ATLAS_ENV_FILE','RUNTIME_MODE','RUNTIME_ID','ATLAS_API_TARGET')
    $atlasDemoSaved = @{}
    foreach ($atlasDemoName in $atlasDemoVariables) {
        $atlasDemoSaved[$atlasDemoName] = [Environment]::GetEnvironmentVariable($atlasDemoName, 'Process')
    }
    try {
        $env:DASHSCOPE_API_KEY = ''
        $env:RESEARCH_MODEL_ENABLED = 'false'
        $env:NEO4J_URI = 'bolt://127.0.0.1:1'
        $env:GROBID_BASE_URL = 'http://127.0.0.1:1'
        & (Join-Path $PSScriptRoot 'start.ps1') -Mode Local -DataDir $atlasDemoData -BackendPort $BackendPort -FrontendPort $FrontendPort -Offline -AllowAnonymous
        if ($LASTEXITCODE -ne 0) { throw 'Demo runtime startup failed' }
        $atlasDemoStarted = Get-Content -LiteralPath $atlasDemoMetadata -Raw | ConvertFrom-Json
        $atlasDemoStarted | Add-Member -NotePropertyName demo_isolated_services -NotePropertyValue $true -Force
        $atlasDemoStarted | ConvertTo-Json | Set-Content -LiteralPath $atlasDemoMetadata -Encoding utf8
    } finally {
        foreach ($atlasDemoName in $atlasDemoVariables) {
            [Environment]::SetEnvironmentVariable($atlasDemoName, $atlasDemoSaved[$atlasDemoName], 'Process')
        }
    }
}

switch ($Action) {
    'Prepare' {
        & $atlasDemoPython $atlasDemoPrepare --data-dir $atlasDemoData --pdf-dir $PdfDir @atlasDemoPrepareOptions
        if ($LASTEXITCODE -ne 0) { throw 'Demo preparation failed' }
    }
    'Check' {
        Test-DemoData
        & (Join-Path $PSScriptRoot 'start.ps1') -Mode Local -DataDir $atlasDemoData -BackendPort $BackendPort -FrontendPort $FrontendPort -Offline -Check
        if ($LASTEXITCODE -ne 0) { throw 'Demo dependency check failed' }
    }
    'Start' { Start-DemoRuntime }
    'Stop' {
        if (Test-DemoRuntimeIdentity) {
            & (Join-Path $PSScriptRoot 'stop.ps1') -Mode Local -BackendPort $BackendPort
        } else { Write-Output 'No managed demo runtime; saved data retained' }
    }
    'Restart' {
        Test-DemoData
        if (Test-DemoRuntimeIdentity) {
            & (Join-Path $PSScriptRoot 'stop.ps1') -Mode Local -BackendPort $BackendPort
        }
        Start-DemoRuntime
    }
    'Status' {
        Test-DemoData
        if (Test-DemoRuntimeIdentity) {
            try { $atlasDemoStatus = Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/system/status" -TimeoutSec 15 }
            catch { Write-Output "Demo is stopped or unavailable; saved data retained: $atlasDemoData"; break }
            if ([IO.Path]::GetFullPath($atlasDemoStatus.data_dir) -ne $atlasDemoData) { throw 'API is using another data profile' }
            $atlasDemoStatus | ConvertTo-Json -Depth 6
        } else { Write-Output "Demo prepared and stopped; data: $atlasDemoData" }
    }
}
