# Research Atlas T6 evaluation assets

This directory is owned by T6. It contains evaluation definitions, scripts, synthetic
fixtures, and run records. It does **not** contain paper PDFs, training data, model
weights, API credentials, or hidden holdout answers.

## Data partitions

- `development`: PaDiM and PatchCore. These sources may be used while building and
  debugging the extraction workflow.
- `same_domain_holdout`: FastFlow. Only source metadata is public here. Human labels
  remain incomplete and must not be disclosed to development tasks before the
  evaluation rules and system version are frozen.
- `cross_domain`: DLinear, PatchTST, and iTransformer. These are a separate transfer
  check, not additional image-anomaly development samples.
- `synthetic`: invented passages and expected outputs used for automated tests. A
  synthetic result is never a real-paper effectiveness result.

`corpus_manifest.json` is the source-of-truth inventory for source identity,
partition, recorded license, and redistribution decision. Public access is not
treated as permission to redistribute.

## Annotation workflow

1. Freeze the evaluation protocol, target Research Atlas build, model, prompts, and
   source versions.
2. Have a human annotator fill records conforming to `annotation_schema.json`.
   Model-generated drafts may assist navigation, but they are not gold labels.
3. Set `annotation_status` to `completed` only after human review. Unfinished records
   remain `incomplete` and are excluded from metric denominators.
4. Store holdout labels outside developer-readable paths until the freeze is signed
   off. This repository intentionally includes no holdout answer file.
5. If any holdout result is used during development, set `contamination.used_by_development`
   to `true`, describe the exposure, and stop calling that material an independent
   holdout.
6. Run `evaluate.py` on a completed JSONL file and retain its JSON output under
   `records/` with the exact command, build identifier, and environment notes.

## Commands

From the repository root:

```powershell
python evaluation/research_atlas/evaluate.py `
  --input evaluation/research_atlas/fixtures/synthetic_annotations.jsonl

powershell -ExecutionPolicy Bypass -File `
  evaluation/research_atlas/run_acceptance.ps1
```

The first command only checks the scorer with invented data. The second runs all
Research Atlas backend tests, all non-Research legacy backend tests, the focused
frontend print-page boundary test, the synthetic scorer self-check, and the static
integration gate. Backend tests use project-local temporary directories; external
HTTP is mocked by the shared test fixture. Neither command invokes a real model,
Neo4j, a paper algorithm, or a browser PDF renderer.

The print test verifies saved/unsaved labels and visible unknown/review states in
jsdom. It does not verify browser pagination, fonts, print CSS rendering, or a generated
PDF file. Those remain manual browser acceptance items.

## Platform execution regression (2026-10-11)

CI also runs `run_assistant_browser.cjs` for existing interactions and
`prepare_platform_fixture.py` + `run_platform_browser.cjs` for a fresh PDF intake,
coverage, reading records, immutable action versions, source change, process restart,
snapshot output, partial failure and narrow screen flow in real Chromium. Both use
isolated synthetic SQLite/PDF data with model and graph services disabled.
`check_local_runtime.ps1` exercises Windows Local start, profile conflicts and restart.
`benchmark_workflow_projection.py` checks warm SQL pagination equality and single
source invalidation on 1,000 papers; measured times have no absolute CI threshold.
See [current platform delivery](../../docs/unified-release.md) for commands and limits.

## 2026-10-17 完整使用与多人边界验收

`backend/tests/test_multiuser_isolation.py` 通过真实应用验证账号之间的论文、PDF、课题、快照导出、任务、取消句柄和后台线程隔离，以及 CSRF、停用账号和基础配额。默认测试环境仍为单用户，且使用临时目录。

真实浏览器受控多人验收（输出目录须全新）：

```powershell
$env:ATLAS_PLAYWRIGHT_PATH = Join-Path (Get-Location) 'frontend/node_modules/playwright'
# 已安装 Playwright 浏览器时可省略；本机已有 Chrome 也可显式使用：
$env:ATLAS_CHROME_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
node evaluation/research_atlas/run_multiuser_browser.cjs .ui_validation/my-multiuser-check
```

脚本创建隔离合成账号，口令仅驻内存，不写入报告；访问仅限本机，退出时停止自己创建的服务。它不迁移现有账号、不接入模型，也不证明公网负载、真实科研质量或容器运行已验收。
