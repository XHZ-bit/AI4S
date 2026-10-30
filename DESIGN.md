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
