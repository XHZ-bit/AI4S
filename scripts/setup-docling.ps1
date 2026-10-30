param(
    [switch]$Check,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$strideRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stridePython = Join-Path $strideRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $stridePython)) { throw 'Run scripts/setup-dependencies.ps1 first.' }
$strideNames = @('HF_HOME','TORCH_HOME','DOCLING_ARTIFACTS_PATH','HF_HUB_DISABLE_SYMLINKS_WARNING','HF_HUB_DISABLE_XET','HF_HUB_DOWNLOAD_TIMEOUT','HF_HUB_ETAG_TIMEOUT','PAPERSTRIDE_MODEL_CHECK','PAPERSTRIDE_MODEL_FORCE')
$strideSaved = @{}
foreach($strideName in $strideNames) { $strideSaved[$strideName] = [Environment]::GetEnvironmentVariable($strideName,'Process') }
try {
    $env:HF_HOME = Join-Path $strideRoot '.tmp\models\huggingface'
    $env:TORCH_HOME = Join-Path $strideRoot '.tmp\models\torch'
    $env:DOCLING_ARTIFACTS_PATH = Join-Path $strideRoot '.tmp\models\docling'
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
    $env:HF_HUB_DISABLE_XET = '1'
    $env:HF_HUB_DOWNLOAD_TIMEOUT = '120'
    $env:HF_HUB_ETAG_TIMEOUT = '30'
    $env:PAPERSTRIDE_MODEL_CHECK = [string][int][bool]$Check
    $env:PAPERSTRIDE_MODEL_FORCE = [string][int][bool]$Force
    @'
from pathlib import Path
import hashlib, json, os
import torch
from docling.utils.model_downloader import download_models

root=Path(os.environ['DOCLING_ARTIFACTS_PATH'])
if os.environ['PAPERSTRIDE_MODEL_CHECK']=='1':
    manifest=root/'paperstride-models.json'
    if not manifest.is_file():
        raise SystemExit('Docling weights missing. Run scripts/setup-docling.ps1 to prepare layout, table, formula and OCR models.')
    state=json.loads(manifest.read_text(encoding='utf-8'))
    missing=[name for name in state['files'] if not (root/name).is_file()]
    if missing:
        raise SystemExit('Docling model cache is incomplete: '+', '.join(missing[:3]))
    for name,expected in state.get('sha256',{}).items():
        with (root/name).open('rb') as model_file:
            actual=hashlib.file_digest(model_file,'sha256').hexdigest()
        if actual!=expected:
            raise SystemExit('Docling model integrity check failed: '+name)
else:
    root.mkdir(parents=True,exist_ok=True)
    download_models(output_dir=root,force=os.environ['PAPERSTRIDE_MODEL_FORCE']=='1',progress=True,
        with_layout=True,with_tableformer=True,with_code_formula=True,
        with_picture_classifier=False,with_rapidocr=True,with_easyocr=False)
    files=[p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '.cache' not in p.parts and p.name!='paperstride-models.json']
    if not files:
        raise SystemExit('Model downloader returned no model files.')
    hashes={}
    for name in files:
        with (root/name).open('rb') as model_file:
            hashes[name]=hashlib.file_digest(model_file,'sha256').hexdigest()
    (root/'paperstride-models.json').write_text(json.dumps({'format':'paperstride-docling-models-v1','files':files,'sha256':hashes},indent=2),encoding='utf-8')
print(json.dumps({'parser':'docling','torch':torch.__version__,'cpu_only':torch.version.cuda is None,'model_cache':str(root)},ensure_ascii=False))
'@ | & $stridePython -X utf8 -
    if($LASTEXITCODE -ne 0) { throw 'Docling setup failed. Existing files and user data were retained; retry this script after resolving connectivity.' }
} finally {
    foreach($strideName in $strideNames) {
        if($null -eq $strideSaved[$strideName]) { Remove-Item -LiteralPath "Env:$strideName" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($strideName,$strideSaved[$strideName],'Process') }
    }
}
