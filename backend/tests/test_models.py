import pytest

from app.models.paper import PaperDoc, normalize_arxiv_id


def test_normalize_arxiv_id():
    assert normalize_arxiv_id("arXiv:2401.12345v3") == "2401.12345"
    assert normalize_arxiv_id("2401.12345v1") == "2401.12345"
    assert normalize_arxiv_id("2401.12345") == "2401.12345"
    assert normalize_arxiv_id("cs/9901001v2") == "cs/9901001"


def test_paper_doc_defaults():
    doc = PaperDoc(uid="2401.12345", title="T", abstract="A", authors=["X"], year=2024)
    assert doc.source == "arxiv"
    assert doc.categories == []


def test_paper_doc_forbids_empty_uid():
    with pytest.raises(ValueError):
        PaperDoc(uid="", title="T", abstract="A", authors=["X"], year=2024)
