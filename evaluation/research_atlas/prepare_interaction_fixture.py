"""Synthetic PDF and resource requirements for offline interaction acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import fitz
from prepare_browser_fixture import prepare_fixture
from app.db.sqlite import connect


def prepare(directory):
    manifest = prepare_fixture(directory)
    directory = Path(manifest["data_dir"])
    pdf = fitz.open()
    quote = "Synthetic requirements: GPU memory 16 GB, count 1, training time 120 min. Not a scientific result."
    for number in range(1, 5):
        page = pdf.new_page()
        page.insert_text((50, 60), f"Research Atlas synthetic interaction fixture / page {number}")
        page.insert_textbox(fitz.Rect(50, 100, 550, 300), quote if number == 2 else "Synthetic teaching document. No model or experiment has been run.", fontsize=14)
    folder = directory / "pdfs"
    folder.mkdir()
    path = folder / f"{manifest['paper_uid']}.pdf"
    pdf.save(path)
    pdf.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with connect(manifest["database_path"]) as conn:
        conn.execute("UPDATE documents SET content_hash=? WHERE id=?", (digest, manifest["document_id"]))
        conn.execute("UPDATE passages SET page=2,text=? WHERE document_id=?", (quote, manifest["document_id"]))
        for table in ("research_paper_link_versions", "research_evidence", "research_snapshots"):
            # These are newly created synthetic fixture payloads, before serving.
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "payload_json" in columns:
                conn.execute(f"UPDATE {table} SET payload_json=replace(payload_json,?,?)", ("synthetic-browser-content-v1", digest))
        for row in conn.execute("SELECT rowid,payload_json FROM research_fact_versions WHERE fact_id='setting-synthetic-a'").fetchall():
            value = json.loads(row["payload_json"])
            value["resources"] = [{"name": n, "value": v, "unit": u, "finding_status": "reported"} for n, v, u in [("device_kind", "GPU", None), ("device_count", 1, None), ("gpu_memory", 16, "GB"), ("training_time", 120, "min"), ("cost", 10, "USD")]]
            for binding in value["field_evidence"]:
                if binding["field_path"] == "resources":
                    binding["finding_status"] = "reported"
                    binding["evidence_ids"] = [manifest["evidence_id"]]
            conn.execute("UPDATE research_fact_versions SET payload_json=? WHERE rowid=?", (json.dumps(value), row["rowid"]))
        rows = conn.execute("SELECT rowid,payload_json FROM research_evidence").fetchall()
        for row in rows:
            value = json.loads(row["payload_json"])
            value["quote"] = quote
            value["locator"] = {**(value.get("locator") or {}), "page": 2}
            conn.execute("UPDATE research_evidence SET payload_json=? WHERE rowid=?", (json.dumps(value), row["rowid"]))
        conn.commit()
    manifest["interaction_fixture"] = True
    (directory / "browser-fixture.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output_dir), ensure_ascii=True))
