param([string]$OutputDir)
$ErrorActionPreference='Stop'
$atlasRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not $OutputDir) { $OutputDir=Join-Path $atlasRoot ".ui_validation\runtime-$([guid]::NewGuid().ToString('N'))" }
$atlasOutput=[IO.Path]::GetFullPath($OutputDir)
$atlasValidation=[IO.Path]::GetFullPath((Join-Path $atlasRoot '.ui_validation'))
if (-not $atlasOutput.StartsWith($atlasValidation+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime acceptance must use an isolated .ui_validation directory' }
if (Test-Path -LiteralPath $atlasOutput) { throw 'Choose a fresh runtime acceptance directory' }
New-Item -ItemType Directory -Path $atlasOutput | Out-Null
$atlasEnvironmentNames=@('DASHSCOPE_API_KEY','RESEARCH_MODEL_ENABLED','OFFLINE_MODE','NEO4J_URI','GROBID_BASE_URL','DATA_DIR','ATLAS_ENV_FILE','RUNTIME_MODE','RUNTIME_ID','ATLAS_API_TARGET','ACCESS_MODE','REGISTRATION_ENABLED','SESSION_SECURE_COOKIE')
$atlasEnvironmentSaved=@{}
foreach ($atlasName in $atlasEnvironmentNames) {
    $atlasEnvironmentSaved[$atlasName]=[Environment]::GetEnvironmentVariable($atlasName,'Process')
}

function Assert-CallerEnvironment([hashtable]$Expected,[string]$Context) {
    foreach ($atlasName in $Expected.Keys) {
        if ([Environment]::GetEnvironmentVariable($atlasName,'Process') -cne $Expected[$atlasName]) {
            throw "Caller environment changed during $Context for $atlasName"
        }
    }
}

function Get-IsolatedPorts {
    $atlasListeners=@()
    try {
        foreach ($atlasIndex in 1..2) {
            $atlasListener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0)
            $atlasListener.ExclusiveAddressUse=$true
            $atlasListener.Start()
            $atlasListeners+=$atlasListener
        }
        return @($atlasListeners | ForEach-Object { $_.LocalEndpoint.Port })
    } finally {
        foreach ($atlasListener in $atlasListeners) { $atlasListener.Stop() }
    }
}

$atlasData=Join-Path $atlasOutput 'data'
$atlasReport=@{fixture='synthetic';checks=@{};passed=$false}
$atlasBackendPort=$null
try {
    # Sentinels are deliberately synthetic; no credential values enter the report.
    $env:DASHSCOPE_API_KEY='synthetic-runtime-acceptance'
    $env:RESEARCH_MODEL_ENABLED='true'
    $env:OFFLINE_MODE='false'
    $env:NEO4J_URI='bolt://127.0.0.1:1'
    $env:GROBID_BASE_URL='http://127.0.0.1:1'
    $env:DATA_DIR=Join-Path $atlasOutput 'caller-data'
    $env:ATLAS_ENV_FILE=Join-Path $atlasOutput 'caller.no-env'
    $env:RUNTIME_MODE='acceptance-caller'
    $env:RUNTIME_ID='acceptance-caller'
    $env:ATLAS_API_TARGET='http://127.0.0.1:1'
    $env:ACCESS_MODE='local'
    $env:REGISTRATION_ENABLED='true'
    $env:SESSION_SECURE_COOKIE='false'
    $atlasExpected=@{}
    foreach ($atlasName in $atlasEnvironmentNames) {
        $atlasExpected[$atlasName]=[Environment]::GetEnvironmentVariable($atlasName,'Process')
    }
    try {
        $env:ACCESS_MODE='multiuser'
        foreach ($atlasMode in @('Local','Docker')) {
            $atlasMultiuserRejected=$false
            try { & "$atlasRoot\start.ps1" -Mode $atlasMode -Check }
            catch {
                if ($_.Exception.Message -notlike 'start.ps1 manages single-user local profiles only.*') { throw }
                $atlasMultiuserRejected=$true
            }
            if (-not $atlasMultiuserRejected) { throw 'Single-user startup accepted a multi-user environment' }
        }
    } finally { $env:ACCESS_MODE=$atlasExpected.ACCESS_MODE }
    Assert-CallerEnvironment $atlasExpected 'rejected multi-user startup'
    $atlasReport.checks.multiuser_profile_rejected_before_launch=$true
    $atlasBackendPort,$atlasFrontendPort=Get-IsolatedPorts
    $atlasApi="http://127.0.0.1:$atlasBackendPort"
    $atlasReport.ports=@{backend=$atlasBackendPort;frontend=$atlasFrontendPort}
    & "$atlasRoot\start.ps1" -Mode Local -Offline -DataDir $atlasData -BackendPort $atlasBackendPort -FrontendPort $atlasFrontendPort
    Assert-CallerEnvironment $atlasExpected 'local startup'
    $atlasReport.checks.local_start_restores_caller_environment=$true
    $atlasPublicSession=Invoke-RestMethod "$atlasApi/api/auth/session" -TimeoutSec 15
    if (-not $atlasPublicSession.require_login) { throw 'Default startup did not require login' }
    $atlasAnonymousBlocked=$false
    try { Invoke-RestMethod "$atlasApi/api/system/status" -TimeoutSec 15 | Out-Null }
    catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 401) { throw }
        $atlasAnonymousBlocked=$true
    }
    if (-not $atlasAnonymousBlocked) { throw 'Anonymous access bypassed the runtime login boundary' }
    $atlasRegistration=@{username='runtime-acceptance';password='isolated runtime acceptance password'} | ConvertTo-Json
    Invoke-RestMethod "$atlasApi/api/auth/register" -Method Post -ContentType 'application/json' -Body $atlasRegistration -SessionVariable atlasHttpSession -TimeoutSec 30 | Out-Null
    $atlasFirst=Invoke-RestMethod "$atlasApi/api/system/status" -WebSession $atlasHttpSession -TimeoutSec 15
    $atlasReport.checks.default_login_boundary_and_isolated_account=$true
    if ($atlasFirst.services.model.status -ne 'unconfigured' -or $atlasFirst.services.model.research_enabled -or -not $atlasFirst.capabilities.local_workspace) { throw 'Offline startup did not enable the local workspace without a model' }
    if ($atlasFirst.services.graph.status -ne 'available' -or $atlasFirst.services.graph.backend -ne 'sqlite-kw' -or $atlasFirst.services.parser.status -ne 'fallback') { throw 'Acceptance runtime did not use the local graph and optional-parser fallback' }
    $atlasReport.checks.child_profile_is_offline_with_local_sqlite_graph=$true
    $atlasProtectedRuntimeRejected=$false
    try { & "$atlasRoot\start.ps1" -Mode Local -Offline -DataDir $atlasData -BackendPort $atlasBackendPort -FrontendPort $atlasFrontendPort }
    catch {
        if ($_.Exception.Message -notlike 'A login-protected runtime already uses this port.*') { throw }
        $atlasProtectedRuntimeRejected=$true
    }
    if (-not $atlasProtectedRuntimeRejected) { throw 'Repeated startup did not reject a login-protected runtime' }
    Assert-CallerEnvironment $atlasExpected 'repeated local startup'
    $atlasRepeated=Invoke-RestMethod "$atlasApi/api/system/status" -WebSession $atlasHttpSession -TimeoutSec 15
    if ($atlasRepeated.pid -ne $atlasFirst.pid) { throw 'Repeated startup changed process identity' }
    $atlasReport.checks.repeated_start_does_not_replace_protected_process=$true
    $atlasRejected=$false
    try { & "$atlasRoot\start.ps1" -Mode Local -Offline -DataDir (Join-Path $atlasOutput 'other-data') -BackendPort $atlasBackendPort -FrontendPort $atlasFrontendPort } catch { $atlasRejected=$true }
    if (-not $atlasRejected) { throw 'Different data profile was silently accepted' }
    Assert-CallerEnvironment $atlasExpected 'rejected data profile'
    $atlasReport.checks.different_data_profile_rejected=$true
    & "$atlasRoot\restart.ps1" -Mode Local -BackendPort $atlasBackendPort
    Assert-CallerEnvironment $atlasExpected 'local restart'
    $atlasRestarted=Invoke-RestMethod "$atlasApi/api/system/status" -WebSession $atlasHttpSession -TimeoutSec 15
    if ($atlasRestarted.runtime_id -eq $atlasFirst.runtime_id -or $atlasRestarted.data_dir -ne $atlasFirst.data_dir -or $atlasRestarted.services.model.status -ne 'unconfigured' -or $atlasRestarted.services.model.research_enabled) { throw 'Restart lost the selected data/offline profile' }
    $atlasReport.checks.restart_preserves_data_and_offline_profile=$true

    # Exercise post-mutation failures without launching another process.
    $atlasFailureBackend,$atlasFailureFrontend=Get-IsolatedPorts
    & {
        function Start-Process {
            if ($env:OFFLINE_MODE -ne 'true') { throw 'Local offline startup did not set OFFLINE_MODE' }
            throw 'Synthetic runtime launch failure'
        }
        $atlasLaunchRejected=$false
        try { & "$atlasRoot\start.ps1" -Mode Local -Offline -DataDir (Join-Path $atlasOutput 'failed-data') -BackendPort $atlasFailureBackend -FrontendPort $atlasFailureFrontend }
        catch {
            if ($_.Exception.Message -ne 'Synthetic runtime launch failure') { throw }
            $atlasLaunchRejected=$true
        }
        if (-not $atlasLaunchRejected) { throw 'Synthetic local launch failure was not raised' }
    }
    Assert-CallerEnvironment $atlasExpected 'failed local startup'
    $atlasReport.checks.local_failure_restores_caller_environment=$true

    # A scoped command double covers Docker environment handling without touching containers.
    & {
        function docker {
            if (($args -join ' ') -ne 'compose up -d --build') { throw 'Unexpected synthetic Docker invocation' }
            if ($env:OFFLINE_MODE -ne 'true') { throw 'Docker offline startup did not set OFFLINE_MODE' }
            Set-Variable -Name LASTEXITCODE -Scope 1 -Value 0
        }
        & "$atlasRoot\start.ps1" -Mode Docker -Offline
    }
    Assert-CallerEnvironment $atlasExpected 'synthetic Docker startup'
    $atlasReport.checks.docker_start_restores_caller_environment=$true
    & {
        function docker {
            if (($args -join ' ') -ne 'compose up -d --build') { throw 'Unexpected synthetic Docker invocation' }
            if ($env:OFFLINE_MODE -ne 'true') { throw 'Docker offline startup did not set OFFLINE_MODE' }
            Set-Variable -Name LASTEXITCODE -Scope 1 -Value 31
        }
        $atlasDockerRejected=$false
        try { & "$atlasRoot\start.ps1" -Mode Docker -Offline }
        catch {
            if ($_.Exception.Message -notlike 'Docker startup failed.*') { throw }
            $atlasDockerRejected=$true
        }
        if (-not $atlasDockerRejected) { throw 'Synthetic Docker startup failure was not raised' }
    }
    Assert-CallerEnvironment $atlasExpected 'failed synthetic Docker startup'
    $atlasReport.checks.docker_failure_restores_caller_environment=$true
    $atlasReport.docker_validation='synthetic command only; no containers started or stopped'
    $atlasReport.passed=$true
} catch {
    $atlasReport.error=$_.Exception.Message
    throw
} finally {
    try {
        if ($atlasBackendPort) {
            $atlasMetadata=Join-Path $atlasRoot ".tmp\run\$atlasBackendPort\runtime.json"
            if (Test-Path -LiteralPath $atlasMetadata) {
                $atlasManaged=Get-Content -LiteralPath $atlasMetadata -Raw | ConvertFrom-Json
                if ([IO.Path]::GetFullPath($atlasManaged.data_dir) -ne $atlasData) { throw 'Acceptance cleanup refused to stop another data profile' }
                & "$atlasRoot\stop.ps1" -Mode Local -BackendPort $atlasBackendPort
            }
        }
        $atlasReport.checks.managed_services_stopped=$true
    } catch {
        $atlasReport.passed=$false
        $atlasReport.cleanup_error=$_.Exception.Message
        throw
    } finally {
        foreach ($atlasName in $atlasEnvironmentNames) {
            if ($null -eq $atlasEnvironmentSaved[$atlasName]) {
                Remove-Item -LiteralPath "Env:$atlasName" -ErrorAction SilentlyContinue
            } else {
                [Environment]::SetEnvironmentVariable($atlasName,$atlasEnvironmentSaved[$atlasName],'Process')
            }
        }
        Assert-CallerEnvironment $atlasEnvironmentSaved 'acceptance cleanup'
        $atlasReport.checks.validation_restores_caller_environment=$true
        $atlasReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $atlasOutput 'runtime-check.json') -Encoding utf8
    }
}
$atlasReport | ConvertTo-Json -Depth 6
