"""Conservative mathematical presentation, without changing source evidence."""

from __future__ import annotations

import re
from urllib.parse import quote


def usable_latex(value):
    if not isinstance(value, str):
        return ""
    text = value.strip().removeprefix("$$").removesuffix("$$").strip()
    if not text or len(text) > 10000 or "\ufffd" in text or re.search(r"[\ue000-\uf8ff]", text):
        return ""
    if text.count("{") != text.count("}") or re.search(r"<[^>]+>", text):
        return ""
    return text


def formula_source(pid, evidence, source, block, *, pdf=False):
    """Only associate a current block with evidence from that exact source version."""
    if block.get("kind") != "formula" or evidence.get("source_version") != source.get("version"):
        return None
    meta = block.get("metadata", {})
    latex = usable_latex(meta.get("latex"))
    page, bbox = block.get("page"), block.get("bbox")
    result = {
        "evidence_id": evidence["id"], "block_id": block["id"], "source_id": source["id"],
        "label": block.get("heading") or "原文公式", "latex": latex,
        "recognition": meta.get("recognition", "not_parsed") if latex else "source_image",
        "page": page,
    }
    if pdf and page and bbox:
        result["image_url"] = (f"/api/projects/{quote(pid, safe='')}/sources/"
                               f"{quote(source['id'], safe='')}/images/{quote(block['id'], safe='')}")
    return result


def learning_quote(evidence):
    formula = evidence.get("formula")
    if formula:
        # Untranscribed PDF glyph order is not a formula transcription.
        return "$$" + formula["latex"] + "$$" if formula.get("latex") else ""
    return evidence.get("quote", "")


def project_learning(value, evidence):
    """Repair only verbatim automatic quotations in old cached lessons, in memory."""
    result = {**value, "sections": dict(value.get("sections", {}))}
    protected = set(value.get("user_edited_sections", []))
    for key, text in result["sections"].items():
        if key in protected or not isinstance(text, str):
            continue
        for item in evidence:
            formula = item.get("formula")
            original = item.get("quote", "")
            if formula and original and original in text:
                # The source-backed formula component renders this once, separately.
                text = text.replace(original, "" if key == "definition" else learning_quote(item))
        result["sections"][key] = text.strip()
    result["formula_sources"] = [item["formula"] for item in evidence if item.get("formula")]
    return result
