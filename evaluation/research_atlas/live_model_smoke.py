"""One authorized, bounded live model request using existing process credentials.

Run inside the configured backend container; never load .env or print secrets.
Only the hard-coded synthetic passage below is sent externally.
"""

import json
import httpx
from app.config import Settings

settings = Settings(_env_file=None)
if not settings.dashscope_api_key:
    raise SystemExit("BLOCKED: process model key is unavailable")
passage = (
    "SYNTHETIC VALIDATION INPUT, NOT SCIENTIFIC RESULTS. The Synthetic Probe method "
    "has two settings: Alpha uses SyntheticImages; Beta uses SyntheticSeries. "
    "GPU memory, runtime and measured scores are not reported."
)
payload = {
    "model": settings.llm_model,
    "messages": [
        {"role": "system", "content": "Extract only the given source. Return JSON with method (the shortest explicit method name as a string, excluding metadata, disclaimers, sentence prefixes and the generic word method), settings (array of name and dataset), gpu_memory, runtime, scores. Unreported fields must be null. No suggestions or invented results."},
        {"role": "user", "content": passage},
    ],
    "response_format": {"type": "json_object"},
    "max_tokens": 1024,
    "temperature": 0,
}
with httpx.Client(timeout=90) as client:
    response = client.post(
        settings.llm_api_base.rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + settings.dashscope_api_key},
        json=payload,
    )
if response.status_code != 200:
    # Do not print error bodies, request headers, or credentials.
    raise SystemExit(f"LIVE MODEL FAILED: HTTP {response.status_code}")
data = response.json()
content = json.loads(data["choices"][0]["message"]["content"])
checks = {
    "method_name_exact": content.get("method") == "Synthetic Probe",
    "settings_separate": {s["name"]: s["dataset"] for s in content.get("settings", [])} == {
        "Alpha": "SyntheticImages", "Beta": "SyntheticSeries"
    },
    "unknowns_preserved": all(k in content and content[k] is None for k in ("gpu_memory", "runtime", "scores")),
}
print(json.dumps({
    "live_model": True, "mock": False, "model": data.get("model", settings.llm_model),
    "requests": 1, "requested_max_tokens": 1024, "synthetic_input_only": True,
    "checks": checks, "observed_synthetic_response": content,
    "usage": data.get("usage"), "finish_reason": data["choices"][0].get("finish_reason"),
}))
if not all(checks.values()):
    raise SystemExit("LIVE MODEL QUALITY GATE FAILED; response is not accepted as a fact")
