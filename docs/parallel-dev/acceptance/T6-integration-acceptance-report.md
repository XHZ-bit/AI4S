# T6 integration acceptance report

Date: 2026-10-04 (Asia/Shanghai)

Verdict: **automated integration gate passed; real-service and browser/PDF release
acceptance remains incomplete**. This is not a real-paper effectiveness claim and is
not approval to deploy publicly or submit competition materials.

## Evidence boundary

- Backend acceptance uses temporary SQLite databases and invented records.
- Model calls and graph writes are mocked; external HTTP is blocked/mocked by the
  shared test fixture.
- The print test runs in jsdom. It does not render or inspect a PDF file.
- The scorer result is synthetic self-validation only. Its 0.5 values are deliberately
  invented test values, not Research Atlas performance.
- No real model, GROBID, Neo4j, paper algorithm, training data, or model weights were
  invoked or downloaded.

## Automated result

The unified command was:

```powershell
powershell -ExecutionPolicy Bypass -File evaluation/research_atlas/run_acceptance.ps1
```

Result:

| Stage | Result | Meaning |
|---|---:|---|
| Research backend suite | 106 passed | Contract, T1-T5, mounted HTTP integration and T6 synthetic checks |
| Non-Research backend regression | 116 passed | All current backend tests whose filename does not start with `test_research` |
| Focused print-page test | 2 passed | Saved/unsaved labels, unknowns and review reasons in jsdom |
| Synthetic scorer | completed | One invented completed record scored; one incomplete record excluded |
| Static integration preflight | 11/11 passed | Required source wiring and boundary tests are present |

T6's own suite contains 14 tests and passed independently in 1.50 seconds. Ruff and
`py_compile` passed for the changed Python files.

## Required scenario status

| Scenario | Result | Boundary |
|---|---|---|
| Human-authored plan fallback | Backend persistence pass | A complete `user_input` plan can be saved and snapshotted without a provider; browser creation UX is not verified |
| No plan provider | Pass | Async task becomes `failed`, has no result, reports `not_implemented`, and preserves prior plans/snapshots |
| Extraction model timeout | Pass at T2 boundary | Mock `httpx.ReadTimeout` raises explicit `ModelInvocationError`; no candidates are produced |
| Graph failure and retry | Pass | Failure preserves snapshot, retry gets a new task ID linked to the failed task, then succeeds under mock graph recovery |
| HTTP 409 | Pass in mounted integration suite | Stale write returns structured conflict with current version and no overwrite |
| Constraint change impact | Pass | Referencing snapshot becomes `needs_review`; unrelated project remains current |
| Fact/evidence impact | Pass | Dependent snapshot is marked while unrelated snapshot remains current |
| JSON export | Pass | Contract version, frozen project/constraint/profile/decision/document/fact versions, source kind and review state are serialized |
| Print boundary | Partial pass | jsdom verifies status labels; real PDF pagination, fonts and print CSS remain unverified |
| Old feature regression | Pass, automated | 116 non-Research backend tests; see `legacy-regression-checklist.md` |

## Manual fallback integration note

The storage/API contract accepts a fully authored `ValidationPlan` through the existing
plan save path, so a model provider is not required to persist and snapshot a human
plan. T6 proved that backend boundary without changing production code.

The current frontend print and edit workflow was not manually exercised in a browser.
T4/T0 should verify that a user can start an empty/manual draft when generation is
unavailable. If the UI still requires a generated draft before editing, add a
frontend-only “新建人工方案” entry using the existing `ValidationPlan` and `PUT` contract;
do not silently convert a failed generation task into success.

## Remaining findings

### RA-T6-002 — Real browser PDF output is unverified

- Severity: release validation, not an automated-code failure.
- Automated evidence: saved snapshots and local drafts are visibly distinguished in
  jsdom, including unknowns and `needs_review` reasons.
- Missing evidence: Chromium/Edge print preview, page breaks, fonts, link rendering,
  and inspection of an actual saved PDF.
- Required follow-up: print one immutable snapshot and one unsaved draft in a supported
  browser, visually inspect every page, and retain screenshots/PDF hashes without
  committing private source content.

### RA-T6-003 — Real service recovery is unverified

- Mock graph failure and retry pass, but real Neo4j availability, credentials,
  transaction behavior and restart recovery were not tested.
- Mock model timeout is explicit, but no authorized provider timeout/retry test was run.
- These tests require separate service/data authorization and must be reported apart
  from mock results.

## Current gate interpretation

- Automated code/integration gate: **PASS**.
- Real browser/PDF gate: **NOT RUN**.
- Real model/GROBID/Neo4j gate: **NOT RUN**.
- Human gold and A/B/C effectiveness gate: **NOT RUN**.
- Public release/submission decision: **not established by T6 automation**.
