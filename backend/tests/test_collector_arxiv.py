from pathlib import Path

import httpx
import respx

from app.collector.arxiv import fetch_topic

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_atom.xml"


@respx.mock
def test_fetch_topic_parses_and_normalizes():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=FIXTURE.read_text())
    )
    with httpx.Client() as client:
        docs = fetch_topic(
            client,
            keywords=["diffusion policy"],
            categories=["cs.RO"],
            start_year=2023,
            max_results=10,
        )
    assert len(docs) == 2
    first = docs[0]
    assert first.uid == "2401.12345"
    assert first.title == "Diffusion Policy for Robot Manipulation"
    assert first.authors == ["Cheng Chi", "Shuran Song"]
    assert first.pdf_url == "http://arxiv.org/pdf/2401.12345v2"
    assert first.year == 2024


@respx.mock
def test_fetch_topic_filters_old_papers():
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=FIXTURE.read_text())
    )
    with httpx.Client() as client:
        docs = fetch_topic(client, ["robot"], ["cs.RO"], start_year=2024, max_results=10)
    assert [d.uid for d in docs] == ["2401.12345"]
