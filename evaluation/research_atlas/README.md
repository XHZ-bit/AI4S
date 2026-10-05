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
