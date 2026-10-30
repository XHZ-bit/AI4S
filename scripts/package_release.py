"""Create a verified source delivery without user data, credentials or caches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
TREES = ("backend/app", "backend/scripts", "backend/tests", "frontend/src", "frontend/scripts", "frontend/public", "scripts", "evaluation", "docs", ".github")
FILES = ("README.md", ".env.example", ".gitignore", "ruff.toml", "start.ps1", "stop.ps1", "restart.ps1", "demo.ps1",
         "docker-compose.yml", "docker-compose.multiuser.yml", "backend/pyproject.toml", "backend/uv.lock", "backend/.python-version", "backend/MANIFEST.in", "backend/Dockerfile", "backend/.dockerignore",
         "frontend/package.json", "frontend/package-lock.json", "frontend/index.html", "frontend/tsconfig.json", "frontend/vite.config.ts", "frontend/vitest.config.ts", "frontend/Dockerfile", "frontend/nginx.conf", "frontend/.dockerignore")
SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".jsonl", ".css", ".html", ".md", ".txt", ".svg", ".ico", ".yml", ".yaml", ".ps1", ".toml", ".csv"}
EXCLUDE = {"__pycache__", "node_modules", ".tmp", ".venv", "pdf-assets", "python-runtime", "records"}
PROJECT_LICENSES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
OPTIONAL_FILES = (*PROJECT_LICENSES, "NOTICE", "NOTICE.md", "THIRD_PARTY_NOTICES.md", "DESIGN.md")
# Keep the review package focused on current operations and contracts. Historical
# evidence stays on disk and in the separately verified local history archive.
CURRENT_DOCS = {
    "docs/unified-release.md", "docs/reproducible-dependencies.md", "docs/workspace-layout.md",
    "docs/knowledge-workspace-contract.md", "docs/local-data-recovery.md",
    "docs/multiuser-backup-recovery.md", "docs/multiuser-trial.md",
    "docs/ui-account-services-2026-10-28.md", "docs/workbench-services.md",
    "docs/research-project-workspace.md", "docs/personal-learning.md",
    "docs/case-study-guide.md", "docs/third-party-case-resources.md",
    "docs/validation/aic-dependency-licenses-2026-10-29.json",
    # check_release_gate.py still checks this compatibility handoff.
    "docs/parallel-dev/handoffs/T5.md",
}


def included_tree_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if set(relative.parts) & EXCLUDE:
        return False
    name = relative.as_posix()
    if relative.parts[0] == "docs":
        if name in CURRENT_DOCS:
            return True
        # Curated current evidence; real-data reports contain aggregates only.
        if len(relative.parts) >= 3 and relative.parts[1] == "validation" and relative.parts[2].startswith("unified-"):
            return path.suffix.lower() in SUFFIXES | {".png", ".jpg", ".jpeg", ".log"}
        return False
    return path.suffix.lower() in SUFFIXES


def package(output: Path, version: str, *, require_license=False):
    output = output.resolve()
    if not output.is_relative_to(ROOT / ".releases"):
        raise ValueError("Release output must be inside this workspace's .releases directory")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,70}", version):
        raise ValueError("Invalid version label")
    project_license = next((name for name in PROJECT_LICENSES
                            if (ROOT / name).is_file() and (ROOT / name).read_text(encoding="utf-8").strip()), None)
    if require_license and project_license is None:
        raise ValueError("No non-empty project license declared; the rights holder must choose one before a final open-source delivery")
    selected = {ROOT / item for item in FILES}
    selected.update(ROOT / item for item in OPTIONAL_FILES if (ROOT / item).is_file())
    for tree in TREES:
        selected.update(path for path in (ROOT / tree).rglob("*") if path.is_file() and included_tree_file(path))
    data = {}
    for path in sorted(selected):
        if not path.is_file():
            raise ValueError(f"Required file missing: {path.relative_to(ROOT)}")
        if not path.resolve().is_relative_to(ROOT) or any(part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()) for part in [path, *path.parents] if part != ROOT.parent):
            raise ValueError("Linked files are not allowed in release inputs")
        raw = path.read_bytes()
        if re.search(rb"\bsk-[A-Za-z0-9_-]{20,}\b", raw):
            raise ValueError(f"Possible credential in {path.relative_to(ROOT)}; review before packaging")
        data[path.relative_to(ROOT).as_posix()] = raw
    manifest = {"version": version, "scope": "source delivery; see README for verified capabilities and outstanding approvals",
                "project_license": project_license,
                "license_check": "Presence only; dependency compatibility and redistribution rights require separate review",
                "excludes": ["user databases", "credentials", "paper PDFs", "node_modules", "virtual environments", "generated PDF/Python runtime assets (restored by npm prebuild)", "historical evaluation outputs", "archived and superseded planning documents", "competition reports and slides"],
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in data.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
        archive.writestr("RELEASE-MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC validation failed")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Archive content mismatch: {name}")
    summary = {"path": str(output), "version": version, "files": len(data), "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--require-license", action="store_true", help="Refuse final open-source delivery without a declared project license")
    args = parser.parse_args()
    package(args.output, args.version, require_license=args.require_license)
