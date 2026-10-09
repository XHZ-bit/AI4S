"""Prepare an isolated, unpublished two-learner Diffusion Policy roadmap demo.

Run with --data-dir pointing to a NEW directory. PDFs stay there; only pinned
source metadata and this script belong in the repository.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.request import urlopen

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.proposals import save_proposal
from app.db.sqlite import connect, upsert_paper
from app.db.workspace import save_document
from app.models.paper import ParsedPaper, Section
from app.roadmap.auto_evaluate import evaluate_candidates


SOURCES = [
    {"arxiv": "2108.03298v2", "sha256": "18283ff9cbb9645de4ccf32ca2de472f452e89761287e7ed578e3a1066bea5f1",
     "title": "What Matters in Learning from Offline Human Demonstrations for Robot Manipulation",
     "year": 2021, "term": "Imitating human demonstrations", "concept": ("concept:imitation-learning", "Imitation learning"), "relation": "USES"},
    {"arxiv": "2006.11239v2", "sha256": "aee5e07a802e8dfd2a386374c94fd61d1d056cb7e1e0fec4f28e8120ff5d8505",
     "title": "Denoising Diffusion Probabilistic Models", "year": 2020,
     "term": "diffusion probabilistic models", "concept": ("concept:diffusion-models", "Diffusion models"), "relation": "USES"},
    {"arxiv": "2303.04137v4", "sha256": "75a57946e2cef790775ca5c667b00befc8ea7d64c3a02c5ced3e3d173354640c",
     "title": "Diffusion Policy: Visuomotor Policy Learning via Action Diffusion", "year": 2023,
     "term": "conditional denoising diffusion process", "concept": ("method:diffusion-policy", "Diffusion Policy"), "relation": "PROPOSES"},
]


def add_relation(conn, paper_uid, passage, relation, src, dst, layer="author_claim"):
    match = re.search(re.escape(relation["term"]), passage["text"], re.IGNORECASE)
    if match is None:
        raise ValueError(f"source phrase not found in {paper_uid}")
    offset = match.start()
    quote = match.group()
    if passage["text"][offset:match.end()] != quote:
        raise ValueError("source offset mismatch")
    payload = {"rel_type": relation["type"], "src_uid": src[0], "src_name": src[1],
               "src_type": "paper" if src[0].startswith("arxiv-") else src[0].split(":", 1)[0], "dst_uid": dst[0],
               "dst_name": dst[1], "dst_type": dst[0].split(":", 1)[0],
               "passage_id": passage["id"], "evidence": quote,
               "conditions": "教学顺序假设；自动检查只确认结构与原文定位" if layer == "teaching" else "来源主题关联；自动检查只确认原文定位"}
    kid = save_proposal(conn, paper_uid, "relation", payload, 0.0)
    conn.execute(
        "INSERT INTO knowledge(id,paper_uid,document_id,passage_id,quote,start_offset,end_offset,layer,status,checks_json) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (kid, paper_uid, passage["document_id"], passage["id"], quote, offset,
         offset + len(quote), layer, "demo_curated",
         '{"structure":true,"evidence_located":true,"semantic":"needs_review","human_review":false}'),
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path, help="new isolated data directory")
    parser.add_argument("--pdf-dir", type=Path, help="optional local cache of the three pinned PDFs")
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit("data directory must be new and empty to protect existing work")
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = data_dir / "pdfs"
    pdf_dir.mkdir()
    conn = connect(str(data_dir / "atlas.db"))
    try:
        target = ("method:diffusion-policy", "Diffusion Policy")
        for source in SOURCES:
            uid = f"arxiv-{source['arxiv']}"
            path = pdf_dir / f"{uid}.pdf"
            raw = ((args.pdf_dir / f"{source['arxiv']}.pdf").read_bytes() if args.pdf_dir
                   else urlopen(f"https://arxiv.org/pdf/{source['arxiv']}", timeout=90).read())
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError(f"PDF hash changed: {source['arxiv']}; inspect source before continuing")
            path.write_bytes(raw)
            doc = fitz.open(stream=raw, filetype="pdf")
            sections = [Section(heading=f"PDF page {i+1}", text=page.get_text(), page=i+1)
                        for i, page in enumerate(doc)]
            upsert_paper(conn, dict(uid=uid, arxiv_id=source["arxiv"].split("v")[0],
                title=source["title"], abstract="", authors=[], year=source["year"],
                venue=None, categories=[], published=None,
                pdf_url=f"https://arxiv.org/pdf/{source['arxiv']}", code_url=None, source="arxiv"))
            did = save_document(conn, uid, ParsedPaper(uid=uid, title=source["title"], abstract="", sections=sections),
                                content_hash=source["sha256"], filename=path.name)
            passage = next((dict(r) for r in conn.execute(
                "SELECT * FROM passages WHERE document_id=? ORDER BY ordinal", (did,))
                if source["term"].casefold() in r["text"].casefold()), None)
            if passage is None:
                raise ValueError(f"could not locate evidence in {source['arxiv']}")
            add_relation(conn, uid, passage, {"type": source["relation"], "term": source["term"]},
                         (uid, source["title"]), source["concept"])
        # A teaching order is an editorial hypothesis, never an author claim.
        dp_uid = f"arxiv-{SOURCES[2]['arxiv']}"
        for source, term in zip(SOURCES[:2], ["behavior cloning formulation",
                                                      "diffusion models for visuomotor policy learning"], strict=True):
            dp_passage = next(dict(r) for r in conn.execute(
                "SELECT pa.* FROM passages pa JOIN documents d ON d.id=pa.document_id "
                "WHERE d.paper_uid=? ORDER BY pa.ordinal", (dp_uid,))
                if term.casefold() in r["text"].casefold())
            add_relation(conn, dp_uid, dp_passage,
                         {"type": "PREREQUISITE_OF", "term": term},
                         source["concept"], target, layer="teaching")
        profiles = {"learner A": ["Imitation learning"], "learner B": ["Diffusion models"]}
        report = evaluate_candidates(conn, target[0], profiles)
        (data_dir / "auto-evaluation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not report["passed"]:
            raise ValueError(f"automated gate failed: {report['failures']}")
        for name, route in report["routes"].items():
            print(f"{name}: {' -> '.join(route)}")
        print(f"Automated checks passed for {report['checked_relations']} relations; "
              f"report: {data_dir / 'auto-evaluation.json'}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
