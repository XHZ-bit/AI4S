# T6 pre-integration acceptance report

> Historical record: this report describes the state before T0 integration. Its
> failures have been re-evaluated. Use `T6-integration-acceptance-report.md` for the
> current result; do not use the verdict below as the current release status.

Date: 2026-10-04 (Asia/Shanghai)

Verdict: **release gate not met**. Module-level synthetic acceptance is largely
available, but T0 integration is not frozen and one T1/T5 semantic graph-query
integration test fails. Real API/model/Neo4j and real-paper effectiveness remain
untested.

## Scope and evidence labels

- All automated business-flow tests use invented records, temporary SQLite databases,
  a mock model, or a mock graph backend.
- The source/license verification uses arXiv metadata and linked license pages only.
- No training data, model weights, paper algorithm, or original paper PDF was
  downloaded or executed.
- The scorer output under `evaluation/research_atlas/records/` is a synthetic
  self-check, not a real-paper score.
- No completed human gold labels exist. FastFlow holdout answers were neither created
  nor used during development, so contamination is currently recorded as false.

## Source and license verification

| Partition | Source | Verified arXiv version | Recorded license | Public artifact decision |
|---|---|---:|---|---|
| Development | PaDiM, arXiv:2011.08785 | v1 | arXiv non-exclusive distribution 1.0 | Metadata/link only |
| Development | PatchCore, arXiv:2106.08265 | v2 | arXiv non-exclusive distribution 1.0 | Metadata/link only |
| Same-domain holdout | FastFlow, arXiv:2111.07677 | v2 | arXiv non-exclusive distribution 1.0 | Metadata/link only; no answers committed |
| Cross-domain | DLinear, arXiv:2205.13504 | v3 | CC BY 4.0 | Conditions recorded; original excluded by default |
| Cross-domain | PatchTST, arXiv:2211.14730 | v2 | arXiv non-exclusive distribution 1.0 | Metadata/link only |
| Cross-domain | iTransformer, arXiv:2310.06625 | v4 | CC BY-NC-ND 4.0 | Noncommercial/unchanged/attributed conditions recorded; original excluded by default |

The arXiv non-exclusive grant authorizes arXiv to distribute; it is not treated as a
general downstream redistribution license. Even for Creative Commons records, the
default public package contains metadata and links rather than paper files.

## Automated coverage

| Required scenario | Current result | Boundary |
|---|---|---|
| Complete project flow | Pass | T1/T3 module orchestration, not the T0-mounted HTTP app |
| Unknown input | Pass | Pydantic rejects extra fields; unknown setting remains `null/unknown` |
| Invalid citation | Pass | Unknown evidence reference rolls back the temporary transaction |
| Same method, different settings | Pass | Two setting records remain separate under one method |
| Wrong metric comparison | Pass | Image/pixel metric scopes are not ranked as equivalent |
| Missing condition | Pass | Missing split produces insufficient/non-comparable output |
| Version conflict | Pass | Stale project version fails without overwrite |
| Model timeout | Pass | Mock timeout raises explicit extraction failure |
| Task retry | Pass | A new task ID references the failed prior task |
| Graph projection failure | Pass | Mock failure preserves SQLite snapshot and marks retryable outbox failure |
| Plan version retention | Pass | Version 1 and edited version 2 remain readable |
| Evidence/fact update impact scope | Pass | Referencing snapshot becomes `needs_review`; unrelated project remains current |
| Old feature regression | Pass, selected set | Health, cases, and roadmap API: 27 tests |

T6-specific pre-integration suite: **10 passed in 1.33s**.

Selected legacy regression: **27 passed in 2.32s**.

All Research Atlas contract/synthetic tests: **95 passed, 1 failed in 2.61s**.

## Failed item

### RA-T6-001 — Semantic graph query modes return no path edges

- Severity: **high / release blocking for graph workflow**.
- Suggested responsibility: T5 owns the query semantics; T1 owns service orchestration
  and the failing integration test. T0 should coordinate the contract-compatible fix.
- Reproduction:
  1. From `backend`, collect all `tests/test_research*.py` files with PowerShell.
  2. Run pytest with a T6-local `--basetemp`.
  3. Observe
     `test_research_t1_storage.py::test_real_t5_three_query_modes_and_sync_status`.
- Expected: `dependency_path` from a decision returns `SELECTS_METHOD`,
  `method_context` returns `HAS_SETTING`, and reverse `impact_path` from evidence
  returns `CITES_EVIDENCE`, plus a status node compatible with T1.
- Actual: the first query returns no edges. `query_project_graph` treats
  `dependency_path/method_context/impact_path` as ordinary node-kind filters instead
  of dispatching to the existing semantic walkers. A second likely mismatch remains:
  T5 emits status in `properties.sync_status`, while the T1 integration assertion
  reads `properties.status`.
- Exact suggestion: in the T5-owned graph query layer, reserve the three semantic
  mode values, require one anchor, dispatch to `explain_dependencies`,
  `explain_method_context`, or `explain_impact`, and return one stable status-property
  shape. Then align the T1 integration assertion and T5 unit tests to that shape.

T6 did not modify either production module.

## Static integration gate failures

`check_release_gate.py` recorded six failed checks:

1. `/api/projects` router not registered in `backend/app/main.py`.
2. Research schema initialization and restart interruption not wired in
   `backend/app/db/sqlite.py`.
3. Research task execution not wired in `backend/app/jobs.py`.
4. T1 imports `app.research.extraction`, while T2 delivered
   `app.research_extraction`; the contract-path adapter is absent.
5. T5 source files exist, but `docs/parallel-dev/handoffs/T5.md` is absent, so T6
   cannot verify the final T5 delivery/integration instructions.
6. Research frontend routes are not registered in `frontend/src/App.tsx`.

These are pre-integration blockers, not claims that the isolated task modules are
otherwise nonfunctional.

## Human evaluation and A/B/C status

- Annotation schema and deterministic scorer: prepared and synthetic self-check passed.
- Development-paper human annotation: not started.
- FastFlow independent holdout annotation: not started; no answer file exists.
- Cross-domain human annotation: not started.
- A original+manual table: not run.
- B ordinary retrieval Q&A: not run; no real model call authorized.
- C Research Atlas full workflow: not run; T0/T5 integration not frozen.
- External user trial: none. Future results must be described as an internal task
  comparison while only team members participate.

No improvement percentage or graph-database causal attribution is claimed.

## Release gate

Current gate: **FAIL**.

To re-evaluate after T0 freeze:

1. Resolve RA-T6-001 and all six static integration checks.
2. Run `evaluation/research_atlas/run_acceptance.ps1` until all automated stages pass.
3. Run browser/API acceptance with a new temporary database.
4. Separately record real model and Neo4j availability; do not substitute mock results.
5. Complete human annotations after freeze, declare contamination, and execute the
   A/B/C internal task protocol if model calls are authorized.
