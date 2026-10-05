"""Read-only Diffusion Policy source inspection. Does NOT run a model.
Python 3.10+, standard library only. Network requests use normal TLS verification.
"""

import argparse
import ast
import hashlib
import json
import platform
import re
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

CASE_ID = "diffusion-policy-intro"
CASE_VERSION = "1.0.0"
COMMIT = "5ba07ac6661db573af695b419a7947ecb704690f"
EXPECTED = {
    "diffusion_policy/policy/base_lowdim_policy.py": "80779d2492f629be926f0788e763fb3d33beba024ed94c4327bc8eae5f4100bb",
    "diffusion_policy/config/task/pusht_lowdim.yaml": "f623b6225002d9d754ec452a8e57c07ae633cf757b388d60fc98773d213eb384",
    "eval.py": "e62694214cce4265ad783d1352713e25e963fb6684365ff1f0f4db08e57ade12",
}


def inspect_sources(contents):
    policy = contents.get("diffusion_policy/policy/base_lowdim_policy.py", "")
    config = contents.get("diffusion_policy/config/task/pusht_lowdim.yaml", "")
    evaluation = contents.get("eval.py", "")
    try:
        tree = ast.parse(policy)
        interface = any(
            isinstance(n, ast.FunctionDef) and n.name == "predict_action"
            for n in ast.walk(tree)
        )
    except SyntaxError:
        interface = False
    values = {
        "python_version": sys.version_info >= (3, 10),
        "policy_interface": interface,
        "observation_shape": "obs: B,To,Do" in policy,
        "action_shape": "action: B,Ta,Da" in policy,
        "observation_dimension": bool(
            re.search(r"^obs_dim:\s*20(?:\s|$)", config, re.M)
        ),
        "action_dimension": bool(re.search(r"^action_dim:\s*2(?:\s|$)", config, re.M)),
        "checkpoint_option": "'--checkpoint', required=True" in evaluation,
        "evaluation_log": "'eval_log.json'" in evaluation,
    }
    return [{"id": key, "passed": value} for key, value in values.items()]


def collect(source_dir=None):
    contents, files, errors = {}, [], []
    for relative, expected in EXPECTED.items():
        try:
            if source_dir is not None:
                path = (source_dir / relative).resolve()
                if not path.is_relative_to(source_dir.resolve()):
                    raise ValueError("Source path escaped source directory")
                with path.open("rb") as handle:
                    data = handle.read(262145)
            else:
                url = f"https://raw.githubusercontent.com/real-stanford/diffusion_policy/{COMMIT}/{relative}"
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(url, timeout=20) as response:
                            if not response.url.startswith(
                                "https://raw.githubusercontent.com/"
                            ):
                                raise ValueError("Unexpected download host")
                            data = response.read(262145)
                        break
                    except (OSError, ValueError):
                        if attempt == 2:
                            raise
                        time.sleep(attempt + 1)
            if len(data) > 262144:
                raise ValueError("Source exceeds 256 KiB")
            digest = hashlib.sha256(data).hexdigest()
            files.append({"path": relative, "sha256": digest})
            if digest != expected:
                errors.append(f"Version mismatch: {relative}")
            contents[relative] = data.decode("utf-8")
        except (OSError, ValueError) as exc:
            # Do not copy proxy URLs, credentials, or arbitrary exception text into reports.
            errors.append(
                f"Cannot read {relative}: {type(exc).__name__}; check path, network and TLS or use offline sources"
            )
    return {
        "schema_version": 1,
        "case_id": CASE_ID,
        "case_version": CASE_VERSION,
        "commit": COMMIT,
        "scope": "source_inspection",
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "files": files,
        "checks": inspect_sources(contents),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Read offline sources; no network or third-party execution",
    )
    parser.add_argument("--output", type=Path, default=Path("atlas-result.json"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Output already exists; choose a new --output filename to preserve history"
        )
    bundle = collect(args.source_dir)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2, allow_nan=False)
    passed = not bundle["errors"] and all(c["passed"] for c in bundle["checks"])
    print(
        f"Source inspection {'passed' if passed else 'needs attention'}: {args.output}"
    )
    print(
        "No model was loaded, trained or evaluated. Import this JSON into Research Atlas."
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
