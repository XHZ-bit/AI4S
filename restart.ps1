param([ValidateSet('Local','Docker')][string]$Mode='Local',[int]$BackendPort=8000)
$ErrorActionPreference='Stop'
if ($Mode -eq 'Docker') { & "$PSScriptRoot\stop.ps1" -Mode Docker; & "$PSScriptRoot\start.ps1" -Mode Docker; exit }
$atlasPath=Join-Path $PSScriptRoot ".tmp\run\$BackendPort\runtime.json"
if (-not (Test-Path -LiteralPath $atlasPath)) { throw 'No managed runtime. Start with an explicit mode and data directory first.' }
$atlasRun=Get-Content -LiteralPath $atlasPath -Raw | ConvertFrom-Json
& "$PSScriptRoot\stop.ps1" -Mode Local -BackendPort $BackendPort
& "$PSScriptRoot\start.ps1" -Mode Local -DataDir $atlasRun.data_dir -BackendPort $atlasRun.backend_port -FrontendPort $atlasRun.frontend_port -Offline:([bool]$atlasRun.offline)
