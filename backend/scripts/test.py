"""Portable pytest entry point with workspace-owned temporary files."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
temporary = root / ".tmp"
temporary.mkdir(exist_ok=True)
run = tempfile.mkdtemp(prefix="pytest-", dir=temporary)
env = {**os.environ, "TEMP": str(temporary), "TMP": str(temporary), "TMPDIR": str(temporary)}
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "--basetemp", str(Path(run) / "tests"), *sys.argv[1:]], cwd=root, env=env))
