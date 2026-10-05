import httpx
import respx

from app.collector.s2 import fetch_citations


@respx.mock
def test_fetch_citations_extracts_arxiv_ids():
    route = respx.get("https://api.semanticscholar.org/graph/v1/paper/arXiv:2401.12345/citations")
    route.mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"externalIds": {"ArXiv": "2013.12345v2"}}},
                    {"citedPaper": {"externalIds": {"DOI": "10.1000/x"}}},
                    {"citedPaper": {}},
                    {"citedPaper": None},
                ]
            },
        )
    )
    with httpx.Client() as client:
        refs = fetch_citations(client, "2401.12345")
    assert refs == ["2013.12345"]


@respx.mock
def test_fetch_citations_retries_on_429(monkeypatch):
    monkeypatch.setattr("app.collector.s2._INITIAL_DELAY", 0)
    route = respx.get("https://api.semanticscholar.org/graph/v1/paper/arXiv:2401.1/citations")
    route.side_effect = [
        httpx.Response(429),
        httpx.Response(200, json={"data": [{"citedPaper": {"externalIds": {"ArXiv": "1111.1"}}}]}),
    ]
    with httpx.Client() as client:
        refs = fetch_citations(client, "2401.1")
    assert refs == ["1111.1"]
