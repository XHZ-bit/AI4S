"""Preserve text and table context from TEI; page locations are optional."""

import xml.etree.ElementTree as ET

_TEI_NS = {"t": "http://www.tei-c.org/ns/1.0"}


def is_alive(client, base):
    return client.get(f"{base}/api/isalive", timeout=5).status_code == 200


def _text(element):
    return " ".join(" ".join(element.itertext()).split()) if element is not None else ""


def parse_with_grobid(client, base, pdf_bytes, filename):
    response = client.post(
        f"{base}/api/processFulltextDocument",
        files={"input": (filename, pdf_bytes, "application/pdf")},
        data={"consolidateHeader": "1"},
        timeout=120,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    sections = []
    for div in root.findall(".//t:body//t:div", _TEI_NS):
        heading = _text(div.find("t:head", _TEI_NS)) or "Untitled"
        for paragraph in div.findall("t:p", _TEI_NS):
            text = _text(paragraph)
            if text:
                sections.append({"heading": heading, "text": text})
    for figure in root.findall(".//t:figure", _TEI_NS):
        table = figure.find("t:table", _TEI_NS)
        if table is None:
            continue
        caption = _text(figure.find("t:figDesc", _TEI_NS))
        title = _text(figure.find("t:head", _TEI_NS)) or "Table"
        rows = [
            [_text(cell) for cell in row.findall("t:cell", _TEI_NS)]
            for row in table.findall("t:row", _TEI_NS)
        ]
        if rows:
            # Keep headers, units and caption with the cells; no inferred numeric claims.
            sections.append(
                {
                    "heading": title,
                    "text": title
                    + "\n"
                    + caption
                    + "\n"
                    + "\n".join(" | ".join(row) for row in rows),
                    "kind": "table",
                    "metadata": {"rows": rows, "caption": caption, "verified": False},
                }
            )
    return {
        "title": _text(root.find(".//t:titleStmt/t:title", _TEI_NS)),
        "abstract": _text(root.find(".//t:profileDesc/t:abstract", _TEI_NS)),
        "sections": sections,
    }
