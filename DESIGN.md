# PaperStride interface

PaperStride is a reading and research workspace. Its interface should keep the current paper, research question, and next action easy to locate. Use a restrained editorial treatment rather than a promotional dashboard.

## Shared visual language

- Light theme uses warm paper white (`#faf9f6`), stone navigation (`#f1f1ea`), dark ink (`#252e2b`), and forest green (`#365e4e`). Dark theme uses neutral green charcoal, warm white text, and a muted sage accent.
- Shared color tokens live in `frontend/src/components/interface.css`; Ant Design tokens in `frontend/src/App.tsx` should match them.
- System sans typography serves Chinese and English reading. Page titles are 28 px on desktop and 25 px on phones. Section headings are 17–20 px; normal controls and copy are 14–15 px. Reserve monospace for code and identifiers.
- Prefer aligned lists and thin separators to repeated cards. Panels that group a real task use a 1 px border, 10 px radius, and no shadow. Controls use a 7 px radius.
- Use green for selected navigation, interactive links, and the primary action. Do not use gradients, decorative badges, or large metric blocks as page scaffolding.
- Keep action labels concrete. Account entry stays visible in the header when signed out. Research lists link directly to the corresponding workspace or paper.

## Layout and states

Desktop has a 232 px navigation rail and a 64 px utility header. Collapsed navigation remains 72 px. Content has generous but bounded horizontal spacing. On phones, navigation moves to the bottom, controls wrap, and two-column sections become a single column.

The home page starts with the current research location, then recent spaces and pending tasks, followed by recent papers. Empty, loading, failure, retry, and populated states remain part of each section. Diagnostics and the example project remain secondary disclosures.

Maintain visible keyboard focus, clear form labels, readable error messages, reduced-motion behavior, and the skip link. Normal text must achieve 4.5:1 contrast. Check both themes at desktop and phone widths after changing shared styles.

## Product messages

- Put useful content and the next action first. Ordinary screens do not repeat implementation notes, generation budgets, or default verification status for every item.
- Separate concrete learning resources from external search shortcuts. Counts and resource filters include concrete records only; a search link is an action, not a retrieved result.
- Put provenance, content-reading status, access records, and verification dates in optional details. A link check does not certify scientific content; reading content does not establish current availability.
- Keep changed evidence, failed operations, invalid links, and unresolved issues that affect the current decision visible, with a recovery action. Preserve user input on failure.
- Use concise, accurate source labels for answers and saved AI notes. Keep model generation, excerpts, teaching supplements, and user judgments distinguishable without repeating a disclaimer in each paragraph.

## Research graph workspace

On desktop, keep project identity, the current question, and graph commands compact so the canvas and node content lead. Empty questions use a direct writing action. Longer questions and path explanations expand on request.

Node details use a resizable split pane, normally 420–560 px wide, with a keyboard accessible separator and an option to expand reading across the workspace. Remember explicit width choices per account and project in the current browser. Resizing or expanding preserves the selected node, drafts, and graph camera. Keep one vertical scroll area for detail content; long formulas and code may scroll horizontally inside their own regions.

## Learning workspace

Keep the personalized explanation action visible outside goal settings. On desktop, group the node title, return, goal settings and generation action in a compact header. The learning view uses the remaining viewport without the global footer or a second bottom padding reservation. Separate lessons, source evidence, and practice into reading tabs with their own scroll positions; chapter selection shares the tab toolbar.

Learning status and the summary entry sit above a right tool pane. Let the reader resize or collapse that pane, with visible shortcuts to questions, notes and records. Those tools switch without discarding drafts or moving the reader. Focus reading temporarily hides global navigation and project chrome while retaining the node identity and generation action; a visible exit and Escape restore the regular workspace. Preserve readable line length rather than stretching paragraphs across the full screen.

Source excerpts belong in a bounded evidence browser, grouped by their relationship to the current node. Preserve exact source locations, identities, and versions when collapsing or deduplicating. Shared math rendering handles prose consistently; code and editable source stay literal, and invalid mathematics offers the original text or source instead of guessed corrections.

## Code practice workspace

On desktop, use the remaining viewport for a task sidebar and a larger code editor with results below it. Keep the exercise title, current goal, version selector, and generation entry compact above the workspace. Do not repeat the node navigation header inside practice.

Switch instructions, input, learning records, and generation settings inside the task sidebar. Switch runtime output and AI feedback below the editor. These switches preserve drafts and keep the same editor mounted. Keep run, check, AI analysis, stop, and save actions between the editor and results, outside their scroll regions.

Allow dragging or keyboard adjustment of task width and result height, with reset and per-account, project, and node preferences in the current browser. Code uses line numbers and literal monospace text. Runtime output appears only after execution; before that, use a concise empty state. Keep unavailable actions and source changes understandable without moving long diagnostics into the main editing space.

## Core work surfaces

Desktop reading, graphs, comparisons, routes and practice share a compact outer frame. Hide the generic footer on these task surfaces and reserve bottom space once. Measure document, editor and comparison viewports from their actual position; fixed percentages of viewport height do not account for controls above them.

Source reading groups document choice, download, formula actions and related knowledge in one command bar. Keep PDF navigation and search in the reader toolbar; secondary details expand without rebuilding the reader. Text and source code scroll inside a bounded document area, and source positioning must not scroll the entire page away from its controls.

Show saved comparison results and saved route steps before configuration. Keep configuration mounted behind an explicit disclosure, preserve pending edits, and retain visible generate, continue and save actions. Comparison tables can scroll in both directions with sticky headings and dimension labels. Materials and research records have direct tabs; existing spaces lead with their sources, while empty spaces show import controls immediately. General dashboards and libraries retain normal document flow.
