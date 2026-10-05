import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.cases.catalog import CASE_ID, SOURCES
from app.db.sqlite import connect

BASE = f"/api/cases/{CASE_ID}"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "atlas_case_check.py"


def checker():
    spec = importlib.util.spec_from_file_location("case_checker", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_bundle(tmp_path):
    for source in SOURCES["files"]:
        path = tmp_path / source["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source["text"].encode())
    return checker().collect(tmp_path)


def new_session(client):
    result = client.post(BASE + "/sessions")
    assert result.status_code == 201
    return result.json()


def test_case_is_offline_and_does_not_claim_model_execution():
    client = TestClient(app)
    case = client.get(BASE).json()
    assert case["scope"] == "source_inspection"
    assert len(case["mappings"]) == 8
    assert all("correct" not in q for q in case["questions"])
    assert "不加载权重" in case["notice"]
    assert "????" not in json.dumps(case, ensure_ascii=False)
    for mapping in case["mappings"]:
        assert mapping["line"] > 0
        assert SOURCES["commit"] in mapping["url"]
    assert client.get("/api/cases/unknown").status_code == 404


def test_offline_bundle_preserves_license_and_byte_hashes():
    client = TestClient(app)
    result = client.get(BASE + "/sources.zip")
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert "MIT License" in archive.read("LICENSE").decode()
        for source in SOURCES["files"]:
            assert (
                hashlib.sha256(archive.read(source["path"])).hexdigest()
                == source["sha256"]
            )
    assert client.get(BASE + "/checker").content == SCRIPT.read_bytes()


def test_sessions_cas_and_answers_are_server_checked():
    client = TestClient(app)
    first = new_session(client)
    url = BASE + "/sessions/" + first["id"]
    updated = client.patch(url, json={"version": 0, "current_step": "interface"}).json()
    assert updated["version"] == 1
    assert (
        client.patch(url, json={"version": 0, "current_step": "config"}).status_code
        == 409
    )
    assert (
        client.patch(url, json={"version": 1, "current_step": "invalid"}).status_code
        == 422
    )
    assert (
        client.patch(
            url, json={"version": 1, "answers": {"scope": {"correct": True}}}
        ).status_code
        == 422
    )
    result = client.post(
        url + "/answers", json={"version": 1, "question_id": "scope", "choice": 0}
    ).json()
    assert result["state"]["answers"]["scope"]["correct"] is False
    second = new_session(client)
    assert second["state"]["answers"] == {}
    assert client.get(url).json()["state"]["answers"]["scope"]["attempts"] == 1


def test_result_import_is_idempotent_and_report_is_honest(tmp_path):
    client = TestClient(app)
    session = new_session(client)
    url = BASE + "/sessions/" + session["id"]
    bundle = valid_bundle(tmp_path)
    result = client.post(url + "/runs", json=bundle)
    assert result.status_code == 200, result.text
    report = result.json()["runs"][0]["report"]
    assert report["passed"] is True
    assert report["status"] == "metadata_consistent"
    assert "不是独立执行认证" in report["verification"]
    assert len(client.post(url + "/runs", json=bundle).json()["runs"]) == 1
    text = client.get(url + "/report").text
    assert "\n## 来源\n" in text
    assert "不报告论文复现成功率" in text
    assert session["id"] in text


@pytest.mark.parametrize(
    "mutation",
    [
        "commit",
        "missing_file",
        "wrong_hash",
        "missing_check",
        "false_check",
        "python",
        "errors",
    ],
)
def test_incomplete_or_inconsistent_runs_never_pass(tmp_path, mutation):
    client = TestClient(app)
    session = new_session(client)
    bundle = valid_bundle(tmp_path)
    if mutation == "commit":
        bundle["commit"] = "0" * 40
    if mutation == "missing_file":
        bundle["files"].pop()
    if mutation == "wrong_hash":
        bundle["files"][0]["sha256"] = "0" * 64
    if mutation == "missing_check":
        bundle["checks"].pop()
    if mutation == "false_check":
        bundle["checks"][0]["passed"] = False
    if mutation == "python":
        bundle["environment"]["python"] = "3.8.0"
    if mutation == "errors":
        bundle["errors"] = ["download failed"]
    result = client.post(BASE + "/sessions/" + session["id"] + "/runs", json=bundle)
    assert result.status_code == 200, result.text
    assert result.json()["runs"][0]["report"]["passed"] is False


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown", "scope", "boolean", "extra", "case_version"]
)
def test_malformed_bundles_are_rejected(tmp_path, mutation):
    client = TestClient(app)
    session = new_session(client)
    bundle = valid_bundle(tmp_path)
    if mutation == "duplicate":
        bundle["files"].append(bundle["files"][0])
    if mutation == "unknown":
        bundle["files"][0]["path"] = "../private"
    if mutation == "scope":
        bundle["scope"] = "paper_reproduction"
    if mutation == "boolean":
        bundle["checks"][0]["passed"] = "true"
    if mutation == "extra":
        bundle["verified"] = True
    if mutation == "case_version":
        bundle["case_version"] = "future"
    assert (
        client.post(
            BASE + "/sessions/" + session["id"] + "/runs", json=bundle
        ).status_code
        == 422
    )


def test_failed_run_remains_latest_and_sessions_are_isolated(tmp_path):
    client = TestClient(app)
    session = new_session(client)
    url = BASE + "/sessions/" + session["id"]
    bundle = valid_bundle(tmp_path)
    client.post(url + "/runs", json=bundle)
    bundle["checks"][0]["passed"] = False
    result = client.post(url + "/runs", json=bundle).json()
    assert len(result["runs"]) == 2
    assert result["runs"][0]["report"]["passed"] is False
    assert new_session(client)["runs"] == []
    assert "记录一致性：需处理" in client.get(url + "/report").text


def test_oversized_import_and_stale_session():
    client = TestClient(app)
    session = new_session(client)
    url = BASE + "/sessions/" + session["id"]
    assert (
        client.post(url + "/runs", content=b"x" * (1024 * 1024 + 1)).status_code == 413
    )
    with connect() as conn:
        conn.execute(
            "UPDATE case_sessions SET case_version='old' WHERE id=?", (session["id"],)
        )
    assert client.get(url).json()["stale"] is True
    assert (
        client.patch(url, json={"version": 0, "current_step": "config"}).status_code
        == 409
    )


def test_checker_cli_runs_offline_and_preserves_previous_output(tmp_path):
    valid_bundle(tmp_path)
    output = tmp_path / "actual-result.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-dir",
            str(tmp_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert bundle["scope"] == "source_inspection"
    assert all(c["passed"] for c in bundle["checks"])
    original = output.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-dir",
            str(tmp_path),
            "--output",
            str(output),
        ],
        capture_output=True,
    )
    assert result.returncode != 0
    assert output.read_bytes() == original


def test_checker_detects_modified_source_without_execution(tmp_path):
    valid_bundle(tmp_path)
    source = tmp_path / SOURCES["files"][0]["path"]
    source.write_text("raise RuntimeError('MUST NOT EXECUTE')", encoding="utf-8")
    result = checker().collect(tmp_path)
    assert result["errors"]
    assert not next(
        c["passed"] for c in result["checks"] if c["id"] == "policy_interface"
    )
