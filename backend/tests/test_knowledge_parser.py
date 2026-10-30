"""Source fidelity and locators for generic workspace parsing; no paid services."""

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pymupdf
import pytest

from app.knowledge.parser import parse_source


def test_python_locates_nested_symbols_without_executing(tmp_path):
    target = tmp_path / "network.py"
    target.write_text(
        'raise RuntimeError("must not run")\nclass Policy:\n    def forward(self, x):\n        return x + 1\n',
        encoding="utf-8",
    )
    result = parse_source(target, "code")
    node = next(
        b for b in result["blocks"] if b["metadata"].get("symbol") == "Policy.forward"
    )
    assert node["metadata"]["start_line"] == 3
    assert node["metadata"]["end_line"] == 4
    assert "return x + 1" in node["text"]
    assert node["page"] is None


def test_repository_locators_pin_file_and_commit(tmp_path):
    target = tmp_path / "source.repo.json"
    target.write_text(
        json.dumps(
            {
                "repository": "https://github.com/example/repo",
                "commit": "a" * 40,
                "files": [
                    {
                        "path": "models/policy.py",
                        "text": "def mean(x):\n    return x\n",
                        "hash": "123",
                        "url": "https://github.com/example/repo/blob/"
                        + "a" * 40
                        + "/models/policy.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = parse_source(target, "code")
    node = next(b for b in result["blocks"] if b["metadata"].get("symbol") == "mean")
    assert node["metadata"]["path"] == "models/policy.py"
    assert node["metadata"]["commit"] == "a" * 40
    assert node["metadata"]["start_line"] == 1
    assert node["metadata"]["end_line"] == 2


def test_csv_preserves_metric_and_cell_locator(tmp_path):
    target = tmp_path / "results.csv"
    target.write_text(
        "method,successes/1000 steps,seed\nA,7.013,9701\n", encoding="utf-8"
    )
    result = parse_source(target, "results")
    block = result["blocks"][0]
    assert block["metadata"]["cells"][0][1] == "successes/1000 steps"
    assert block["metadata"]["cells"][1][1] == "7.013"
    assert block["metadata"]["cell_range"] == "A1:C2"
    assert block["page"] is None


def test_xlsx_keeps_source_formula_and_sheet_locator(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "measurements.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Trial"
    sheet.append(["seed", "ratio"])
    sheet.append([42, "=1/3"])
    book.save(path)
    result = parse_source(path, "results")
    block = result["blocks"][0]
    assert block["metadata"]["sheet"] == "Trial"
    assert block["metadata"]["cells"][1][1] == "=1/3"
    assert block["metadata"]["formula_values"] == "source_formula_not_evaluated"


def test_markdown_preserves_formula_and_heading(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text(
        "# Policy\n\n## Gate\n\n$$\\delta = cs\\tanh(2m/c)$$\n", encoding="utf-8"
    )
    result = parse_source(path, "report")
    formula = next(b for b in result["blocks"] if b["kind"] == "formula")
    assert result["title"] == "Policy"
    assert formula["heading"] == "Gate"
    assert formula["metadata"]["latex"] == r"\delta = cs\tanh(2m/c)"


def test_docx_preserves_fraction_structure_without_invented_pages(tmp_path):
    path = tmp_path / "report.docx"
    xml = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>My study</w:t></w:r></w:p>
      <w:p><m:oMath><m:f><m:num><m:r><m:t>x</m:t></m:r></m:num><m:den><m:r><m:t>y</m:t></m:r></m:den></m:f></m:oMath></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>score</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
      </w:body></w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    result = parse_source(path, "report", use_docling=False)
    formula = next(b for b in result["blocks"] if b["kind"] == "formula")
    assert formula["metadata"]["latex"] == r"\frac{x}{y}"
    assert result["title"] == "My study"
    assert all(b["page"] is None and b["bbox"] is None for b in result["blocks"])
    assert result["quality"]["table_count"] == 1


def make_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page(width=900, height=600)
    page.insert_text((60, 60), "A Study of Coordinated Policies", fontsize=22)
    page.insert_text((60, 90), "with Bounded Information Exchange", fontsize=22)
    page.insert_text((60, 145), "1 Introduction", fontsize=14)
    page.insert_text(
        (60, 180), "This document studies policy coordination.", fontsize=11
    )
    doc.save(path)
    doc.close()


def test_pdf_fallback_keeps_real_dimensions_and_partial_status(tmp_path):
    path = tmp_path / "paper.pdf"
    make_pdf(path)
    result = parse_source(path, "paper", False)
    assert "with Bounded Information Exchange" in result["title"]
    assert result["quality"]["status"] == "partial"
    assert result["quality"]["formula_status"] == "not_parsed"
    assert result["warnings"]
    for block in result["blocks"]:
        assert block["page"] == 1
        assert block["metadata"]["page_width"] == 900
        assert 0 <= block["bbox"][0] < block["bbox"][2] <= 900
        assert 0 <= block["bbox"][1] < block["bbox"][3] <= 600


def test_docling_failure_is_not_reported_as_full_structure(tmp_path, monkeypatch):
    from app.knowledge import parser

    path = tmp_path / "paper.pdf"
    make_pdf(path)

    def unavailable(*args):
        raise RuntimeError("model not installed")

    monkeypatch.setattr(parser, "_docling", unavailable)
    result = parse_source(path, "paper")
    assert result["parser"] == "pymupdf-layout"
    assert result["quality"]["status"] == "partial"
    assert any("RuntimeError" in message for message in result["warnings"])


def test_worker_stdout_is_single_json_result(tmp_path):
    path = tmp_path / "notes.md"
    path.write_text("# Test\n\nStudy notes.", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.knowledge.parser_worker",
            "--input",
            str(path),
            "--kind",
            "report",
            "--no-docling",
        ],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["title"] == "Test"


def test_bad_json_is_an_explicit_failure(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{bad}", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_source(path, "results")


def test_empty_formula_region_and_bottom_left_coordinates_are_preserved(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from app.knowledge import parser
    import docling.document_converter as converter

    path = tmp_path / "paper.pdf"
    make_pdf(path)
    item = SimpleNamespace(
        label="formula",
        text="",
        self_ref="#/texts/0",
        prov=[
            SimpleNamespace(
                page_no=1,
                bbox=SimpleNamespace(
                    l=60, t=400, r=300, b=380, coord_origin="BOTTOMLEFT"
                ),
            )
        ],
    )
    document = SimpleNamespace(
        pages={1: SimpleNamespace(size=SimpleNamespace(width=900, height=600))},
        iterate_items=lambda: iter([(item, 1)]),
    )

    class FakeConverter:
        def __init__(self, **kwargs):
            pass

        def convert(self, path):
            return SimpleNamespace(document=document, status="success")

    monkeypatch.setattr(converter, "DocumentConverter", FakeConverter)
    monkeypatch.setenv('PAPERSTRIDE_FORMULA_MODE','bounded')
    monkeypatch.setenv("PAPERSTRIDE_FORMULA_BUDGET_SECONDS", "0")
    result = parser._docling(path)
    block = result["blocks"][0]
    assert block["kind"] == "formula"
    assert block["bbox"] == [60, 200, 300, 220]
    assert block["metadata"]["latex"] == ""
    assert result["quality"]["formula_coverage"]["total"] == 1
    assert result["quality"]["formula_coverage"]["recognized"] == 0
    assert result["quality"]["status"] == "partial"


def test_html_keeps_math_anchors_and_links_without_script_content(tmp_path):
    path = tmp_path / "paper.html"
    path.write_text(
        "<html><head><title>Study</title></head><body><h1>Policy paper</h1>"
        '<h2 id="method">Method</h2><p>See <a href="https://example.org/code">code</a>.</p>'
        '<math alttext="x^2"><mi>x</mi><mn>2</mn></math>'
        "<table><tr><th>Metric</th><th>Value</th></tr><tr><td>steps</td><td>10</td></tr></table>"
        "<script>do_not_include_this()</script></body></html>",
        encoding="utf-8",
    )
    result = parse_source(path, "paper")
    assert result["title"] == "Policy paper"
    assert all("do_not_include_this" not in block["text"] for block in result["blocks"])
    assert (
        next(block for block in result["blocks"] if block["kind"] == "formula")[
            "metadata"
        ]["latex"]
        == "x^2"
    )
    assert next(block for block in result["blocks"] if block["kind"] == "table")[
        "metadata"
    ]["cells"][1] == ["steps", "10"]
    assert any(
        "https://example.org/code" in block["metadata"].get("urls", [])
        for block in result["blocks"]
    )


def test_formula_budget_zero_preserves_regions_and_reports_no_recognition(
    tmp_path, monkeypatch
):
    from app.knowledge.parser import _bounded_enrich_formulas

    path = tmp_path / "paper.pdf"
    make_pdf(path)
    blocks = [
        {
            "kind": "formula",
            "heading": "Method",
            "text": "source text",
            "page": 1,
            "bbox": [60, 150, 300, 180],
            "metadata": {"latex": "", "recognition": "not_parsed"},
        }
    ]
    monkeypatch.setenv("PAPERSTRIDE_FORMULA_BUDGET_SECONDS", "0")
    coverage, warnings = _bounded_enrich_formulas(path, blocks)
    assert (
        coverage["total"] == 1
        and coverage["recognized"] == 0
        and coverage["attempted"] == 0
    )
    assert blocks[0]["text"] == "source text" and blocks[0]["metadata"]["latex"] == ""
    assert warnings


def test_formula_budget_prioritizes_method_before_appendix(tmp_path, monkeypatch):
    from app.knowledge import parser

    path = tmp_path / "paper.pdf"
    make_pdf(path)
    blocks = [
        {
            "kind": "formula",
            "heading": heading,
            "text": "raw",
            "page": 1,
            "bbox": [60, 150, 300, 180],
            "metadata": {"latex": "", "recognition": "not_parsed"},
        }
        for heading in ["Appendix", "Method", "Introduction"]
    ]

    class Worker:
        returncode = 0

        def __init__(self, command, **kwargs):
            request = Path(command[command.index("--formula-input") + 1])
            output = Path(command[command.index("--formula-output") + 1])
            payload = json.loads(request.read_text(encoding="utf-8"))
            assert [image["index"] for image in payload["images"]] == [1]
            output.write_text(
                json.dumps(
                    {"attempted": [1], "results": [{"index": 1, "latex": "x^2"}]}
                ),
                encoding="utf-8",
            )

        def wait(self, timeout):
            return 0

    monkeypatch.setenv("PAPERSTRIDE_FORMULA_MAX_ITEMS", "1")
    monkeypatch.setenv("PAPERSTRIDE_FORMULA_BUDGET_SECONDS", "5")
    monkeypatch.setattr(parser.subprocess, "Popen", Worker)
    coverage, warnings = parser._bounded_enrich_formulas(path, blocks)
    assert coverage == {
        "total": 3,
        "selected": 1,
        "attempted": 1,
        "recognized": 1,
        "mode": "bounded",
    }
    assert blocks[1]["metadata"]["latex"] == "x^2"
    assert blocks[0]["metadata"]["latex"] == ""
    assert warnings
