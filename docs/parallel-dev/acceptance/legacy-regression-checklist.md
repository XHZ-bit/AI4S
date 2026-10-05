# Legacy feature regression checklist

Date: 2026-10-04

The unified T6 runner executes every backend `test_*.py` file except files beginning
with `test_research`. Result: **116 passed in 5.09 seconds** using the shared isolated
test fixture. This protects old behavior while the Research workspace is integrated.

## Automated areas

- [x] Health and configuration startup
- [x] Existing papers, collection, search and parser APIs
- [x] Citation and evidence workspace behavior
- [x] Existing graph API and Neo4j client adapter tests
- [x] Existing proposal behavior
- [x] Roadmap API, DB, generation, graph algorithms, scoring and signals
- [x] Existing fixed cases, including the retained Diffusion Policy case
- [x] Pipeline extraction, alignment and schema tests
- [x] Review API and SQLite regression
- [x] Release integrity and smoke tests
- [x] LLM client behavior under mocked external HTTP

The exact command is maintained in
`evaluation/research_atlas/run_acceptance.ps1`; it discovers the current non-Research
test inventory rather than relying on a short hand-picked subset.

## Not replaced by automation

- [ ] Open and inspect pre-existing user papers and learning records in a copied or
  disposable database; do not migrate the production database during validation.
- [ ] Manually open the retained Diffusion Policy case in the UI.
- [ ] Verify restart behavior with a temporary database directory.
- [ ] Verify real GROBID, model provider and Neo4j only after explicit authorization.
- [ ] Back up and rehearse restore before any future production-data schema upgrade.

Passing this checklist does not prove real external services are available and does
not authorize changing or clearing an existing data volume.
