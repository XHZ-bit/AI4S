# Knowledge workspace implementation contract

Unless explicitly written as an absolute `/api/...` path, endpoints below are relative to `/api/projects/{project_id}` and use the account-scoped SQLite connection and `project_or_404` checks. PaperStride 1.0 also exposes the account graph described below. Active knowledge reads use `kw_*`; historical frozen snapshots retain their original meaning.

## Unified account graph and interactive learning (1.0)

- `GET /api/knowledge/graph` accepts optional `project_id`, `q`, `kind`, `paper_uid`, `node_id`, `limit` and `offset`. Omitting a project gives the account overview; `project_id=library` selects unassigned library knowledge. A project-only route does not accept the library scope as a project.
- `GET /api/knowledge/nodes/{node_id}` and `/api/knowledge/edges/{edge_id}` accept optional `project_id` and return scoped records and evidence. Old integer IDs resolve through stored mappings. `/api/graph/*` is a compatibility projection of unified knowledge, not a separate Neo4j read model.
- `GET /knowledge/paths?source={node_id}&kind=prerequisites&max_depth=4` returns existing nodes, edges, paths and explicit cycle/truncation information. `kind=connection` additionally accepts `target`. No missing relationship is invented.
- `GET/PATCH /knowledge/nodes/{node_id}/progress` reads/writes `{status,expected_version?}` with `not_started|in_progress|understood|review`. Progress is personal self-assessment; executing code does not set mastery.
- `GET/POST /knowledge/nodes/{node_id}/resources` reads or adds titled HTTP(S) resource links. Resource metadata separates access status, fetched content and source attribution. Local images may include an `evidence` object for returning to the exact block.
- `POST /knowledge/nodes/{node_id}/question` accepts `{question}` and returns an answer, citations, related node/edge IDs, warnings and `model_used`. Only explicit POST may invoke the one-request question budget; without a usable model, the answer stays limited to saved evidence.

Browser practice output may emit a line beginning `PAPERSTRIDE_VISUAL:` followed by bounded JSON for `line|bar|scatter|table`. Charts use finite numeric points and text labels; tables use scalar cells. Raw HTML is never an output format. Saved learning, comparison and practice artifacts remain associated outputs, not independently verified graph facts.

## Source and analysis

- `GET /sources` (optional `include_removed=true`) -> `{items: Source[], preferences: {mode: 'explore'|'research'|'reproduce', view: string|null}, model: {configured: boolean, enabled: boolean}}`.
- `POST /sources` multipart: `file`, optional `kind` (`paper|report|results|code`). Returns `{source: Source, analysis: AnalysisRun}`. Upload automatically queues analysis.
- `POST /sources/link` JSON `{url, kind?: 'paper'|'code'}` -> same response.
- `POST /sources/attach` JSON `{paper_uid}` -> same response; existing papers reused.
- `GET /sources/{id}` -> Source including `blocks: Block[]` and `knowledge_nodes: {id,label,kind,block_ids:string[]}[]` for source-to-knowledge navigation.
- `GET /sources/{id}/file` -> original file.
- `GET /sources/{id}/images/{block_id}` -> saved source image when available.
- `PATCH /sources/{id}` JSON `{removed?: boolean, title?: string}` -> Source.
- `POST /analysis` JSON `{source_id, retry?: boolean}` -> AnalysisRun.
- `GET /analysis` -> `{items: AnalysisRun[]}`; `POST /analysis/{id}/cancel` -> AnalysisRun.
- `GET/PATCH /knowledge/preferences` JSON `{mode?, view?}` -> `{mode,view}`.

`Source`: `{id,project_id,asset_id,version,title,filename,kind,media_type,paper_uid,url,removed,created_at,analysis?: AnalysisRun,blocks?:Block[],knowledge_nodes?:object[],quality?:object,parser?:string,reported_at?:string,reported_at_evidence?:object}`.

`Block`: `{id,ordinal,kind,heading,text,page,bbox?:number[]|null,metadata:object}`; metadata may contain latex, image_url, sheet, cells, start_line, end_line, symbol, language. DOCX uses ordinal/heading, not invented page numbers.

`AnalysisRun`: `{id,project_id,source_id,status,stages: {save,parse,extract,graph},progress,errors:string[],warnings:string[],usage:object,created_at,updated_at}`. Status is `queued|running|succeeded|partial|failed|interrupted|cancelled`. Each stage is `pending|running|done|partial|failed|skipped`.

Generic source context reads actual saved report blocks to identify report cutoffs/record dates, retaining the block, quote and precision in `reported_at_evidence`. It checks cited local paths only against current-space uploaded files and fetched repository manifest paths. It never opens the referenced local paths, executes code or calls models. Node metadata may include `reported_at`, `reported_at_evidence`, `missing_source`, `referenced_paths` and `missing_paths`; user-protected fields are retained. A public file sharing a basename with a private referenced path does not establish the private implementation's availability.

Public GitHub repository snapshots save repository URL, immutable commit, selected files, per-file path/hash/URL and selection coverage. A supported `.py`/`.md`/`.txt` URL of the form `https://github.com/{owner}/{repo}/blob/{40-character-commit}/{path}` directly snapshots the selected immutable raw file without repository-tree/commit API calls. First-batch source material also includes actual `source/coordex/coordex/policies/actor_critic_coord_residual.py` at CoorDex commit `9a5dfe0f52efd2624507f8cc9ed117aef6ef7472`; this is public code, not personal research code. Snapshot coverage is not full repository coverage.

## Knowledge

- `GET /knowledge/graph` params `source_id?, node_id?, q?, kind?, limit?, include_hidden?, overview?` -> `{nodes:Node[],edges:Edge[],total_nodes,total_edges,truncated}`. Overview projects source roots and cross-source relations; projected edge metadata retains `original_source` and `original_target`. Explicit source/node/search/type requests use detail mode.
- `GET /knowledge/nodes/{id}` -> `{node:Node,edges:Edge[],neighbors:Node[],evidence:Evidence[],prerequisites:Node[],resources:object[],demos:string[]}`.
- `PATCH /knowledge/nodes/{id}` JSON `{expected_version, label?, summary?, latex?, hidden?, research_status?}` -> Node. Formula correction is per space and retains the shared original.
- `PATCH /knowledge/edges/{id}` JSON `{expected_version, label?, explanation?, hidden?}` -> Edge.
- `POST /knowledge/nodes/merge` JSON `{node_ids:string[],label?:string}`; `POST /knowledge/nodes/{id}/split` restores merged members.

`Node`: `{id,project_id,source_id,kind,label,summary,parent_id,origin,research_status,version,hidden,source_missing,evidence_ids:string[],metadata:object}`. kinds include `paper|report|results|code|problem|contribution|method|module|experiment|finding|limitation|concept|formula|algorithm|resource|hypothesis`.

`Edge`: `{id,project_id,source_id,source,target,kind,label,explanation,origin,version,hidden,source_missing,evidence_ids:string[],metadata?:object}`.

`Evidence`: `{id,source_id,source_title,block_id,quote,locator:{page?,bbox?,heading?,ordinal?,start_line?,end_line?,sheet?,cell_range?,path?,commit?,url?},source_version,origin}`. Origins are `source|inference|user`. PDF bbox coordinates use top-left original PDF page points. Research statuses are `unspecified|proposed|implemented|reported_result|pending_validation`; status and provenance are independent.

## Learning and comparison

- `GET /knowledge/nodes/{id}/learning` -> LearningArtifact (basic saved content even before generation).
- `POST /knowledge/nodes/{id}/learning` JSON `{refresh?:boolean}` -> LearningArtifact.
- `PATCH /knowledge/nodes/{id}/learning` JSON `{expected_revision:int>=1, sections?:Partial<Sections>, hidden_sections?:SectionKey[]}` -> LearningArtifact. Each supplied section is at most 25000 characters. Concurrent stale revisions return conflict; regenerating preserves user-edited sections and hidden selections, including after source updates.
- `GET /knowledge/comparisons` -> `{items:Comparison[]}`.
- `POST /knowledge/comparisons` JSON `{source_ids:string[],focus_node_ids?:string[],refresh?:boolean}` -> Comparison. Select 2–8 sources and at most one visible `method|module|algorithm|hypothesis` node per source, with at most 8 focused nodes. Focus selection participates in cache identity.

`LearningArtifact`: `{id,node_id,node_version,status,stale,cached,sections:{overview,definition,derivation,prerequisites,implementation,limitations},evidence:Evidence[],resources:object[],demos:string[],usage:object,errors:string[],revision:int,user_edited_sections:SectionKey[],hidden_sections:SectionKey[],origin:string,quality?:object}`. Section values are strings. `SectionKey` is one of the six section keys. Status is `basic|ready|partial|failed`; initial revision is 1. Editing/hiding marks the artifact as user content while per-section edit lists retain its scope. Resources expose `title,url,reason,type,fetched` and optional fetched content internally; a bare resource URL is not source content. Demo IDs are `chain_rule|activations|gating|gaussian|ppo|branches`.

`Comparison`: `{id,source_ids,focus_node_ids:string[],focus_nodes:{id,source_id,label}[],title,rows:{dimension,values:{source_id,text,node_ids:string[],evidence_ids:string[],origin}[],compatibility:string}[],evidence:Evidence[],status,cached,stale,usage:object,errors:string[],completed_dimensions?:string[]}`.

Learning generation includes source-consistency model review within its existing 4-request budget, sharing that budget with any formula-image fallback. The current source and neighboring formulas take precedence; other papers may only be explicit comparisons, and teaching derivations must preserve original definitions, coefficients and scope. Source facts without evidence remain unknown. Failed generation/review or an unresolved original formula retains usable basic content with `partial/basic` status. `ready` denotes completed processing, not independent scientific validation.

Comparisons have an independent 8-request budget. With more than 3 sources, the 8 dimensions run in 4 groups of 2; each group has one generation and one source-consistency review. With fewer sources, the dimensions may be generated/reviewed together. Reviewed groups checkpoint `completed_dimensions` for continuation. Missing evidence is explicitly unknown in the affected cell; an unknown cell does not by itself make the whole comparison partial. `ready` means the processing completed, including correctly preserved unknowns, and is not independent scientific validation. Generation/review failure or interrupted budget yields usable `partial/basic` content. Check method ownership, shared-policy branches versus independent agents, units, original versus adapted implementation, conditions and report dates. The approved plan did not separately set a comparison request limit; 8 is the current implementation default, not a change to the learning limit.

Unchanged defaults: source analysis has up to 16 model calls, global knowledge-model concurrency is 2, and parser concurrency is 1. GET endpoints do not trigger paid generation. Budgets and model review do not imply measured accuracy, cost or elapsed-time guarantees; actual v2 results belong in the acceptance record after verification.

Parser agent contract: `app.knowledge.parser.parse_source(path: Path, kind: str, use_docling: bool = True) -> {title:str,blocks:list[dict],quality:dict,parser:str,warnings:list[str]}`. Block dictionaries follow Block above except id (assigned by storage). `parser_worker` CLI outputs one JSON result on stdout and diagnostics on stderr. No model calls or database writes inside parser.

Implementation locations: `backend/app/knowledge/` contains the ledger and experience services; `backend/app/api/knowledge*.py` contains scoped routes; `frontend/src/api/knowledge.ts` and `knowledgeExperience.ts` define the frontend contracts. Contract changes must preserve scope checks, saved revisions and historical compatibility.
