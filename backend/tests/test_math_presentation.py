"""Bad PDF glyph streams are never promoted into mathematical transcriptions."""

import hashlib
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db import projects
from app.db.sqlite import connect
from app.knowledge import extraction, learning, sources, store
from app.knowledge.math_content import formula_source, project_learning, usable_latex
from app.main import app
from app.models.research import ResearchProjectCreate


RAW = "c_t = fcoord\n\ufffd\nsb,p\nt , sh,p\nt\n\ufffd\n(4)"


def fixture_formula(tmp_path):
    path = tmp_path / "example.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 90), "f(x) = x + 1")
        pdf.save(path)
    conn = connect()
    try:
        pid = projects.create_project(conn, ResearchProjectCreate(title="Formula presentation", domain="custom",
            research_question="Read actual equations", constraints={"version": 1, "objective": "Learn"})).id
    finally:
        conn.close()
    src = sources.ingest(pid, path.read_bytes(), "example.pdf")
    parsed = {"title": "Fixture", "parser": "fixture", "warnings": [], "quality": {}, "blocks": [
        {"ordinal": 0, "kind": "formula", "text": RAW, "heading": "Method", "page": 1, "bbox": [65, 70, 220, 95],
         "metadata": {"latex": "", "recognition": "not_parsed", "original_text": RAW}},
        {"ordinal": 1, "kind": "text", "text": "Own definition.", "heading": "Method", "page": 1, "bbox": [65, 100, 250, 130], "metadata": {}}]}
    with store.connection(pid) as conn:
        store.put_parse(conn, src["asset_id"], parsed)
        blocks = store.source_blocks(conn, src["asset_id"])
        eid = store.add_evidence(conn, pid, src, blocks[0])
        formula = extraction.node(src, "formula", "formula", "Source equation", RAW, [eid], metadata={"latex": "", "block_id": blocks[0]["id"]})
        store.put_record(conn, "kw_nodes", formula)
    return pid, src, formula, blocks, path


def test_bad_glyphs_use_exact_source_crop_and_leave_saved_evidence_unchanged(tmp_path):
    pid, src, node, blocks, path = fixture_formula(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with store.connection(pid) as conn:
        saved = conn.execute("SELECT data FROM kw_evidence WHERE id=?", (node["evidence_ids"][0],)).fetchone()[0]
        value = learning.basic(conn, pid, node["id"])
        assert RAW not in json.dumps(value["sections"])
        formula = value["formula_sources"][0]
        assert formula["latex"] == "" and formula["page"] == 1
        assert blocks[0]["id"] in formula["image_url"]
        assert conn.execute("SELECT data FROM kw_evidence WHERE id=?", (node["evidence_ids"][0],)).fetchone()[0] == saved
    with TestClient(app) as client:
        image = client.get(formula["image_url"])
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
        pix = pymupdf.Pixmap(image.content)
        assert pix.width >= (220 - 65) * 2
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_definition_uses_node_evidence_not_unrelated_neighbor_quotes(tmp_path):
    pid, src, formula, blocks, _ = fixture_formula(tmp_path)
    with store.connection(pid) as conn:
        eid = store.add_evidence(conn, pid, src, blocks[1])
        node = extraction.node(src, "module", "module", "Current method", "A current summary", [eid])
        store.put_record(conn, "kw_nodes", node)
        edge = extraction.edge(src, node["id"], formula["id"], "USES", "uses", "An adjacent equation", formula["evidence_ids"])
        store.put_record(conn, "kw_edges", edge)
        assert len(learning.detail(conn, pid, node["id"])["evidence"]) == 2
        basic = learning.basic(conn, pid, node["id"])
        assert basic["sections"]["definition"] == "Own definition."
        assert basic["formula_sources"] == []


def test_valid_source_latex_is_used_without_rewriting_original_quote(tmp_path):
    pid, src, node, blocks, _ = fixture_formula(tmp_path)
    with store.connection(pid) as conn:
        block = blocks[0]
        block["metadata"].update(latex=r"c_t=f_{\mathrm{coord}}(s_t)", recognition="extracted_unverified")
        conn.execute("UPDATE kw_blocks SET data=? WHERE id=?", (store.encode(block), block["id"]))
        value = store.evidence(conn, pid, node["evidence_ids"])[0]
        assert value["quote"] == RAW
        assert value["formula"]["latex"] == r"c_t=f_{\mathrm{coord}}(s_t)"
        stale = {**value, "source_version": "sha256:different"}
        assert formula_source(pid, stale, src, block, pdf=True) is None


def test_old_cached_lesson_is_projected_without_mutating_its_saved_version(tmp_path):
    pid, _, node, _, _ = fixture_formula(tmp_path)
    with store.connection(pid) as conn:
        saved = learning.basic(conn, pid, node["id"])
        saved["sections"]["definition"] = RAW
        saved["evidence"] = [{k: v for k, v in e.items() if k != "formula"} for e in saved["evidence"]]
        raw = store.encode(saved)
        conn.execute("INSERT INTO kw_learning VALUES(?,?,?,?)", (pid, node["id"], "historical-context", raw))
        projected = learning.get_learning(conn, pid, node["id"])
        assert projected["sections"]["definition"] == ""
        assert projected["formula_sources"] and projected["evidence"][0]["formula"]
        assert conn.execute("SELECT data FROM kw_learning WHERE project_id=?", (pid,)).fetchone()[0] == raw


def test_cached_projection_preserves_user_edits_and_never_guesses_missing_math():
    evidence = [{"id": "e", "quote": RAW, "formula": {"latex": "", "block_id": "b"}}]
    saved = {"sections": {"definition": "Text.\n\n" + RAW}, "user_edited_sections": []}
    assert project_learning(saved, evidence)["sections"]["definition"] == "Text."
    saved["user_edited_sections"] = ["definition"]
    assert project_learning(saved, evidence)["sections"]["definition"].endswith(RAW)
    assert saved["sections"]["definition"].endswith(RAW)


@pytest.mark.parametrize("latex", ["x=\ufffd", r"\frac{x}{", "<script>x</script>", "x=\ue002"])
def test_invalid_transcriptions_are_not_usable_latex(latex):
    assert usable_latex(latex) == ""
