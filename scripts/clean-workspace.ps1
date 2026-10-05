<#
Preview by default. -Apply removes only allowlisted generated artifacts.
-ArchiveLegacyPlans also archives four retired plans before removing them.
No user data, browser profiles, dependencies, evidence, or backups are targets.
#>
[CmdletBinding()]
param([switch]$Apply, [switch]$ArchiveLegacyPlans)

$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$prefix = $workspaceRoot.TrimEnd('\') + '\'
$targets = [Collections.Generic.List[string]]::new()
$drafts = @(
    'docs/superpowers/plans/2026-09-21-m1-m2-data-pipeline.md',
    'docs/superpowers/plans/2026-09-21-m3-extraction-review.md',
    'docs/superpowers/plans/2026-09-21-m4-frontend.md',
    'docs/superpowers/plans/2026-09-21-m5-m6-roadmap-seed.md'
)

function Assert-SafePath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target escapes workspace: $absolute"
    }
    $current = $absolute
    while ($current -and $current.StartsWith($workspaceRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing link: $current" }
        }
        if ($current -eq $workspaceRoot) { break }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}

foreach ($relative in @('.ruff_cache', '.pytest_cache', 'backend/.pytest_cache', 'backend/.ruff_cache', 'frontend/tsconfig.tsbuildinfo')) {
    $path = Join-Path $workspaceRoot $relative
    if (Test-Path -LiteralPath $path) { $targets.Add($path) }
}
Get-ChildItem -LiteralPath (Join-Path $workspaceRoot 'backend') -Directory -Force |
    Where-Object { $_.Name -match '^\.pytest_tmp[^\\]*$|^\.pytest-tmp$' } |
    ForEach-Object { $targets.Add($_.FullName) }
foreach ($relative in @('backend/app', 'backend/tests', 'backend/scripts')) {
    $base = Join-Path $workspaceRoot $relative
    Assert-SafePath $base
    Get-ChildItem -LiteralPath $base -Directory -Recurse -Force |
        Where-Object { $_.Name -eq '__pycache__' } | ForEach-Object { $targets.Add($_.FullName) }
}
$existingDrafts = @()
if ($ArchiveLegacyPlans) {
    $existingDrafts = @($drafts | Where-Object { Test-Path -LiteralPath (Join-Path $workspaceRoot $_) })
    foreach ($relative in $existingDrafts) { $targets.Add((Join-Path $workspaceRoot $relative)) }
}

# Verify every resolved target and all descendants before any destructive action.
$inventory = @(foreach ($path in ($targets | Sort-Object -Unique)) {
    Assert-SafePath $path
    $item = Get-Item -LiteralPath $path -Force
    $children = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $path -Force -Recurse) } else { @($item) }
    if (@($children | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
        throw "Refusing target containing links: $path"
    }
    $files = @($children | Where-Object { -not $_.PSIsContainer })
    [PSCustomObject]@{Path=$path; Files=$files.Count; Bytes=($files | Measure-Object Length -Sum).Sum}
})
$inventory | Format-Table -AutoSize
if (-not $Apply) { Write-Output 'PREVIEW ONLY: no files changed. Use -Apply after review.'; return }

$backupDirectory = Join-Path $workspaceRoot '.local-backups'
Assert-SafePath $backupDirectory
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$runId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$archivePath = $null
if ($existingDrafts.Count) {
    Add-Type -AssemblyName System.IO.Compression
    $archivePath = Join-Path $backupDirectory "retired-plans-$runId.zip"
    $archive = [IO.Compression.ZipFile]::Open($archivePath, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($relative in $existingDrafts) {
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $workspaceRoot $relative), $relative) | Out-Null
        }
    } finally { $archive.Dispose() }
    $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        foreach ($relative in $existingDrafts) {
            $stream = $archive.GetEntry($relative).Open()
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
            finally { $stream.Dispose(); $sha.Dispose() }
            if ($hash -ne (Get-FileHash -LiteralPath (Join-Path $workspaceRoot $relative) -Algorithm SHA256).Hash) {
                throw "Archive verification failed: $relative"
            }
        }
    } finally { $archive.Dispose() }
}

# Generated audit output, not source: retain exact targets and recovery location.
$manifestPath = Join-Path $backupDirectory "cleanup-$runId.json"
$manifest = [ordered]@{status='prepared'; archive=$archivePath; targets=$inventory; deleted=@()}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
try {
    foreach ($entry in $inventory) {
        Assert-SafePath $entry.Path
        Remove-Item -LiteralPath $entry.Path -Recurse -Force -ErrorAction Stop
        $manifest.deleted += $entry.Path
        $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    }
    $manifest.status = 'completed'
} catch {
    $manifest.status = 'failed'
    throw
} finally {
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
}
Write-Output "Deleted targets: $($manifest.deleted.Count); Manifest: $manifestPath; Draft archive: $archivePath"
