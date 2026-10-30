"""The source handoff preserves declarations and cannot silently include local data."""

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest


@pytest.fixture
def release(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/package_release.py"
    spec = importlib.util.spec_from_file_location("source_delivery_audit", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "FILES", ("README.md", ".env.example"))
    monkeypatch.setattr(module, "TREES", ("backend/app",))
    (tmp_path / "README.md").write_text("Synthetic package fixture", encoding="utf-8")
    (tmp_path / ".env.example").write_text("DASHSCOPE_API_KEY=\n", encoding="utf-8")
    (tmp_path / "backend/app").mkdir(parents=True)
    (tmp_path / "backend/app/main.py").write_text("# synthetic source", encoding="utf-8")
    return module, tmp_path


def test_final_delivery_requires_declared_license_without_creating_archive(release):
    module, root = release
    output = root / ".releases/final.zip"
    with pytest.raises(ValueError, match="rights holder"):
        module.package(output, "test-final", require_license=True)
    assert not output.exists()


def test_delivery_includes_license_and_notices_but_excludes_runtime_secrets(release):
    module, root = release
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        (root / name).write_text("Synthetic declaration fixture, not a project license choice", encoding="utf-8")
    (root / ".env").write_text("private synthetic settings", encoding="utf-8")
    (root / "backend/data").mkdir()
    (root / "backend/data/atlas.db").write_bytes(b"private synthetic data")
    output = root / ".releases/final.zip"
    module.package(output, "test-final", require_license=True)
    with ZipFile(output) as archive:
        assert {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"} <= set(archive.namelist())
        assert ".env" not in archive.namelist()
        assert not any("atlas.db" in name for name in archive.namelist())
        manifest = json.loads(archive.read("RELEASE-MANIFEST.json"))
        assert manifest["project_license"] == "LICENSE"
        assert "LICENSE" in manifest["files"]


def test_generated_python_runtime_is_excluded_as_a_unit(release, monkeypatch):
    module, root = release
    monkeypatch.setattr(module, "TREES", ("backend/app", "frontend/public"))
    runtime = root / "frontend/public/python-runtime"
    runtime.mkdir(parents=True)
    (runtime / "pyodide.mjs").write_text("// synthetic generated vendor runtime", encoding="utf-8")
    (runtime / "pyodide-lock.json").write_text("{}", encoding="utf-8")
    (runtime / "pyodide.asm.wasm").write_bytes(b"synthetic binary")
    output = root / ".releases/audit.zip"
    module.package(output, "test-audit")
    with ZipFile(output) as archive:
        assert not any("python-runtime/" in name for name in archive.namelist())


def test_current_docs_and_explicit_acceptance_images_exclude_history(release, monkeypatch):
    module, root = release
    monkeypatch.setattr(module, "TREES", ("backend/app", "docs"))
    included = ["docs/unified-release.md", "docs/knowledge-workspace-contract.md",
        "docs/parallel-dev/handoffs/T5.md", "docs/validation/unified-2026-10-30.md",
        "docs/validation/unified-clean-install-2026-10-30.md", "docs/validation/unified-2026-10-30/graph.png"]
    excluded = ["docs/archive/README-old.md", "docs/implementation-status.md",
        "docs/parallel-dev/handoffs/T0.md", "docs/validation/old-private-screen.png",
        "docs/validation/old-run.json", "docs/validation/unified-2026-10-30/atlas.db"]
    for name in included + excluded:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic fixture", encoding="utf-8")
    output = root / ".releases/current.zip"
    module.package(output, "1.0.0")
    with ZipFile(output) as archive:
        assert set(included) <= set(archive.namelist())
        assert not set(excluded) & set(archive.namelist())
