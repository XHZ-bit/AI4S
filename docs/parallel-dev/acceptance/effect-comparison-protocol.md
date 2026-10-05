# Research Atlas A/B/C internal task comparison protocol

Status: protocol draft, not yet executed. This is an **internal task comparison**;
no external users have participated.

## Purpose

Compare work quality and human effort under three workflows without attributing the
whole-system effect to the graph database alone:

- **A — Original text + manual table:** participants read the frozen source and fill
  the annotation template manually.
- **B — Ordinary retrieval Q&A:** the same model receives the same frozen source set
  and task questions, but does not use Research Atlas project, evidence review,
  condition comparison, versioning, or snapshot workflow.
- **C — Research Atlas:** the same model and frozen source set are used through the
  complete project workflow, including human review and corrections.

## Freeze and allocation

Before any scored run, record:

1. Research Atlas build identifier and contract version.
2. Model provider, exact model/version, temperature and other generation settings.
3. Source IDs, arXiv versions, document hashes and partition.
4. Task wording, required output fields, time start/stop rules and allowed tools.
5. Participant ID, relevant experience, and condition order.
6. Protocol version and gold-label version.

Use the same task instances across A/B/C. Counterbalance condition order when more
than one team member participates. Do not tune prompts or product behavior against
same-domain holdout outcomes after the freeze.

## Primary measures

- Automatic extraction exact precision, recall and omissions at field level.
- Human additions, corrections and removals per final confirmed field.
- Condition-check accuracy for `compatible`, `incompatible`, and `insufficient`.
- Citation-location success rate against human-verified evidence positions.
- Validation-plan structural completeness for objective, selected route, data/split,
  metrics, steps and risks.
- Total elapsed minutes, including preparation, review and correction.

Report raw counts with rates. Do not compare reported metric values across different
datasets, splits, protocols or scopes. Do not infer missing compute, time, or result
values.

## Contamination rule

FastFlow is the same-domain holdout. Until the protocol, system build and annotator
instructions are frozen, only its bibliographic/license metadata may be shared. If a
development decision uses a FastFlow score, error analysis, gold field, or expected
condition result, record the exposure and reclassify it as development material.

## Execution status

- A: not run.
- B: not run; no real model call is authorized.
- C: not run; T0 integration and T5 are not frozen.
- Human gold labels: incomplete.

No effectiveness improvement percentage is available or claimed.

