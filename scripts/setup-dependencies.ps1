param(
    [string]$Python = '3.11.17',
    [switch]$Production,
    [switch]$SkipFrontend,
    [switch]$SkipParserModels,
    [switch]$Direct
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or -not [Environment]::Is64BitProcess) {
    throw 'This bootstrap supports Windows x64. See docs/reproducible-dependencies.md for other platforms.'
}
$atlasRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$atlasVersion = '0.13.1'
$atlasTools = Join-Path $atlasRoot ".tmp\tools\uv-$atlasVersion"
$atlasUv = Join-Path $atlasTools 'uv.exe'
$atlasBackend = Join-Path $atlasRoot 'backend'

function Get-AtlasDownload([string]$Url, [string]$Destination, [switch]$Resume) {
    $atlasCurl = (Get-Command curl.exe -ErrorAction Stop).Source
    $atlasDownloadArgs = @('--fail','--silent','--show-error','--location','--connect-timeout','15','--max-time','600')
    if ($Resume -and (Test-Path -LiteralPath $Destination)) { $atlasDownloadArgs += @('--continue-at','-') }
    if ($Direct) { $atlasDownloadArgs += @('--noproxy','*') }
    & $atlasCurl @atlasDownloadArgs '--output' $Destination $Url
    if ($LASTEXITCODE -ne 0) { throw 'Dependency bootstrap download failed. Check connectivity, or explicitly use -Direct if the system proxy is unavailable.' }
}

function Get-AtlasManagedPython {
    if ($Python -match '^\d+\.\d+\.\d+$') {
        $atlasManaged = Join-Path $atlasRoot ".tmp\tools\python\cpython-$Python-windows-x86_64-none\python.exe"
        if (Test-Path -LiteralPath $atlasManaged) { return $atlasManaged }
    }
    return $null
}

if (-not (Test-Path -LiteralPath $atlasUv)) {
    New-Item -ItemType Directory -Force -Path $atlasTools | Out-Null
    # The official uv PyPI wheel contains the standalone executable; no global
    # Python or pip installation is needed to extract it.
    $atlasMetadataPath = Join-Path $atlasTools 'pypi.json'
    Get-AtlasDownload "https://pypi.org/pypi/uv/$atlasVersion/json" $atlasMetadataPath
    $atlasMetadata = Get-Content -LiteralPath $atlasMetadataPath -Raw | ConvertFrom-Json
    if ($atlasMetadata.info.version -ne $atlasVersion) { throw 'Unexpected uv package version' }
    $atlasWheelName = "uv-$atlasVersion-py3-none-win_amd64.whl"
    $atlasWheel = $atlasMetadata.urls | Where-Object { $_.filename -eq $atlasWheelName }
    if (@($atlasWheel).Count -ne 1 -or $atlasWheel.digests.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Official uv Windows wheel metadata is invalid' }
    $atlasWheelUri = [uri]$atlasWheel.url
    if ($atlasWheelUri.Scheme -ne 'https' -or $atlasWheelUri.Host -ne 'files.pythonhosted.org') { throw 'Unexpected uv package download host' }
    $atlasWheelPath = Join-Path $atlasTools $atlasWheelName
    Get-AtlasDownload $atlasWheel.url $atlasWheelPath -Resume
    if ((Get-FileHash -LiteralPath $atlasWheelPath -Algorithm SHA256).Hash -ne $atlasWheel.digests.sha256) { throw 'Official uv wheel SHA256 mismatch' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $atlasArchive = [IO.Compression.ZipFile]::OpenRead($atlasWheelPath)
    try {
        $atlasEntry = @($atlasArchive.Entries | Where-Object { $_.FullName -match '/uv\.exe$' })
        if ($atlasEntry.Count -ne 1) { throw 'The uv wheel does not contain exactly one executable' }
        $atlasInput = $atlasEntry[0].Open()
        try {
            $atlasOutput = [IO.File]::Open($atlasUv, [IO.FileMode]::CreateNew)
            try { $atlasInput.CopyTo($atlasOutput) } finally { $atlasOutput.Dispose() }
        } finally { $atlasInput.Dispose() }
    } finally { $atlasArchive.Dispose() }
}
$atlasActualVersion = & $atlasUv --version
if ($LASTEXITCODE -ne 0 -or $atlasActualVersion -notmatch '^uv 0\.13\.1(?:\s|$)') { throw 'Expected repository-local uv 0.13.1; the existing executable was not replaced' }

$atlasVariableNames = @('UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_PYTHON_BIN_DIR','UV_PYTHON_CACHE_DIR','UV_PYTHON_INSTALL_BIN','UV_PYTHON_INSTALL_REGISTRY','UV_PROJECT_ENVIRONMENT','UV_LINK_MODE','NPM_CONFIG_CACHE','TEMP','TMP','TMPDIR','NO_PROXY')
$atlasSaved = @{}
foreach ($atlasName in $atlasVariableNames) { $atlasSaved[$atlasName] = [Environment]::GetEnvironmentVariable($atlasName,'Process') }
try {
    $env:UV_CACHE_DIR = Join-Path $atlasRoot '.tmp\uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $atlasRoot '.tmp\tools\python'
    $env:UV_PYTHON_BIN_DIR = Join-Path $atlasRoot '.tmp\tools\python-bin'
    $env:UV_PYTHON_CACHE_DIR = Join-Path $atlasRoot '.tmp\tools\python-cache'
    $env:UV_PYTHON_INSTALL_BIN = 'false'
    $env:UV_PYTHON_INSTALL_REGISTRY = 'false'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $atlasBackend '.venv'
    $env:UV_LINK_MODE = 'copy'
    # Keep npm's cache local as well: inherited global cache paths may be
    # unavailable to a restricted review account. Restore the caller's setting
    # in finally; do not change npm's user/global configuration.
    $env:NPM_CONFIG_CACHE = Join-Path $atlasRoot '.tmp\npm-cache'
    $atlasTemporary = Join-Path $atlasRoot '.tmp\dependencies'
    New-Item -ItemType Directory -Force -Path $atlasTemporary | Out-Null
    $env:TEMP = $atlasTemporary
    $env:TMP = $atlasTemporary
    $env:TMPDIR = $atlasTemporary
    if ($Direct) { $env:NO_PROXY = '*' }
    $atlasSyncPython = Get-AtlasManagedPython
    if (-not $atlasSyncPython) { $atlasSyncPython = $Python }
    $atlasSyncArgs = @('sync','--project',$atlasBackend,'--locked','--python',$atlasSyncPython)
    if (-not $Production) { $atlasSyncArgs += @('--extra','dev') }
    & $atlasUv @atlasSyncArgs
    if ($LASTEXITCODE -ne 0 -and $atlasSyncPython -eq $Python) {
        # Restricted Windows accounts may deny uv's optional global minor-version
        # links after the Python download succeeded. Use the verified local
        # installation directly; application startup never needs those links.
        $atlasManaged = Get-AtlasManagedPython
        if ($atlasManaged) {
            Write-Output 'Retrying with the repository-managed Python executable.'
            $atlasSyncArgs[5] = $atlasManaged
            & $atlasUv @atlasSyncArgs
        }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Locked backend installation failed; no global Python packages were changed' }
    if (-not $SkipParserModels) {
        & (Join-Path $PSScriptRoot 'setup-docling.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Structural parser model setup failed' }
    }
    if (-not $SkipFrontend) {
        Push-Location (Join-Path $atlasRoot 'frontend')
        try {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'Frontend npm ci failed' }
        } finally { Pop-Location }
    }
    Write-Output "Backend Python: $(Join-Path $atlasBackend '.venv\Scripts\python.exe')"
    Write-Output 'Dependencies installed from lock files. Use start.ps1 -Mode Local or demo.ps1.'
} finally {
    foreach ($atlasName in $atlasVariableNames) {
        if ($null -eq $atlasSaved[$atlasName]) {
            Remove-Item -LiteralPath "Env:$atlasName" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($atlasName,$atlasSaved[$atlasName],'Process')
        }
    }
}
