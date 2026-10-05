$ErrorActionPreference = "Stop"
$evaluationRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $evaluationRoot)
$backendRoot = Join-Path $projectRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend"
$pytestTemp = Join-Path $evaluationRoot ".tmp\pytest"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $pytestTemp) | Out-Null

Set-Location -LiteralPath $backendRoot
$researchTests = Get-ChildItem -LiteralPath "tests" -Filter "test_research*.py" -File |
  Sort-Object Name |
  ForEach-Object { $_.FullName }
& python -m pytest -q @researchTests --basetemp=$pytestTemp
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$legacyTests = Get-ChildItem -LiteralPath "tests" -Filter "test_*.py" -File |
  Where-Object { $_.Name -notlike "test_research*.py" } |
  Sort-Object Name |
  ForEach-Object { $_.FullName }
& python -m pytest -q @legacyTests --basetemp=$pytestTemp
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location -LiteralPath $frontendRoot
& npm test -- src/__tests__/research/print.test.tsx
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location -LiteralPath $projectRoot
python evaluation/research_atlas/evaluate.py `
  --input evaluation/research_atlas/fixtures/synthetic_annotations.jsonl
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python evaluation/research_atlas/check_release_gate.py
exit $LASTEXITCODE
