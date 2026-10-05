import fitz
import httpx
import respx

from app.parser.service import parse_pdf


def _make_pdf(title: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), title)
    page.insert_text((72, 100), "We study reinforcement learning for robots.")
    return doc.tobytes()


def test_fallback_parses_text_without_grobid():
    parsed = parse_pdf("upload-test", _make_pdf("Fallback Title"), filename="t.pdf")
    assert parsed.uid == "upload-test"
    assert "reinforcement learning" in parsed.abstract or any(
        "reinforcement learning" in s.text for s in parsed.sections
    )


@respx.mock
def test_grobid_path_used_when_alive():
    respx.get("http://fake-grobid/api/isalive").mock(return_value=httpx.Response(200, text="true"))
    respx.post("http://fake-grobid/api/processFulltextDocument").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<TEI xmlns='http://www.tei-c.org/ns/1.0'>"
                "<teiHeader><fileDesc><titleStmt><title>Grobid Title</title></titleStmt>"
                "<profileDesc><abstract><p>Grobid abstract.</p></abstract></profileDesc>"
                "</fileDesc></teiHeader>"
                "<text><body><div><head>1. Intro</head><p>Body text.</p></div></body></text>"
                "</TEI>"
            ),
        )
    )
    parsed = parse_pdf("upload-x", _make_pdf("anything"), filename="t.pdf", grobid_base="http://fake-grobid")
    assert parsed.title == "Grobid Title"
    assert parsed.abstract == "Grobid abstract."
    assert parsed.sections[0].heading == "1. Intro"
