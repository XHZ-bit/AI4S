"""Prepare exact outbound requests offline; execution requires the approved hash."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MODEL = "qwen3.7-flash-2026-07-15"
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings  # noqa: E402
from app.models.research import ExtractionInput  # noqa: E402
from app.research import model_runtime  # noqa: E402
from app.research_extraction import candidates  # noqa: E402
from app.research_extraction.prompts import build_messages  # noqa: E402

SAMPLES = [
    ("name_boundary", "synthetic", "SYNTHETIC TEST ONLY. Our method is called CedarProbe. CedarProbe uses patch embeddings. The notice is not part of the method name.", None),
    ("separate_settings", "synthetic", "CedarProbe has settings Alpha and Beta. Alpha uses SyntheticTiles with split S1. Beta uses SyntheticTiles with split S2. Alpha image AUROC is 0.81. Beta image AUROC is 0.73.", None),
    ("result_ownership", "synthetic", "Our method CedarProbe is evaluated in setting Alpha on SyntheticTiles: image AUROC 0.81. The cited BirchBaseline method uses setting Beta on SyntheticTiles: image AUROC 0.76. BirchBaseline is not our method.", None),
    ("missing_resources", "synthetic", "CedarProbe uses setting Alpha on SyntheticTiles. The passage provides no GPU memory, runtime, random seed or measured accuracy. These quantities must remain unknown.", None),
    ("negation", "synthetic", "CedarProbe uses setting Alpha on SyntheticTiles. CedarProbe does not use pixel labels. The proposed score 0.99 was not measured and must not be treated as a result.", None),
    ("metric_scope", "synthetic", "CedarProbe uses setting Alpha on SyntheticTiles. Alpha image AUROC is 0.81. Alpha pixel AUROC is 0.92. CedarProbe setting Beta uses SyntheticTiles with a different split: image AUROC is 0.74.", None),
    ("padim_excerpt", "public_excerpt", "PaDiM makes use of a pretrained convolutional neural network (CNN) for patch embedding", "https://arxiv.org/abs/2011.08785v1"),
    ("patchcore_excerpt", "public_excerpt", "MVTec AD benchmark PatchCore achieves an image-level anomaly detection AUROC score of up to $99.6\\%$", "https://arxiv.org/abs/2106.08265v2"),
]


def extraction_input(identity, text):
    now = "2026-10-22T00:00:00Z"
    digest = hashlib.sha256(text.encode()).hexdigest()
    return ExtractionInput.model_validate({
        "project_id": "approval-review", "domain": "image_anomaly_detection", "domain_profile_version": "image-anomaly-v1",
        "paper_link": {"id": f"link-{identity}", "project_id": "approval-review", "version": 1, "paper_uid": identity, "role": "method",
                       "linked_document_id": identity, "linked_document_version": f"excerpt:{digest}", "created_at": now, "updated_at": now},
        "document": {"paper_link_id": f"link-{identity}", "paper_uid": identity, "document_id": identity, "document_version": f"excerpt:{digest}", "content_hash": digest},
        "passages": [{"id": f"passage-{identity}", "document_id": identity, "text": text, "page": None, "heading": "Abstract excerpt" if identity.endswith("excerpt") else "Original synthetic input", "kind": "text"}],
    })


def prepare(path):
    requests = []
    for identity, scope, text, url in SAMPLES:
        value = extraction_input(identity, text)
        raw = value.passages[0]
        messages = build_messages(passage={"document_id": identity, "passage_id": raw["id"], "text": text, "page": None, "heading": raw["heading"], "kind": "text"},
                                  domain=value.domain, domain_profile_version=value.domain_profile_version,
                                  output_schema=candidates._PassageExtraction.model_json_schema())
        size = len(json.dumps(messages, ensure_ascii=False).encode())
        if size > 60000:
            raise ValueError("Input exceeds frozen budget")
        requests.append({"id": identity, "scope": scope, "source_url": url, "input": value.model_dump(mode="json"), "messages": messages, "input_utf8_bytes": size})
    manifest = {"version": "model-review-v2", "status": "awaiting_user_approval", "model": MODEL,
                "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1", "max_requests": 8,
                "max_output_tokens": 8192, "enable_thinking": False, "timeout_seconds": 60, "automatic_retries": 0,
                "schema_require_all": False,
                "response_format": {"type": "json_schema", "json_schema": {"name": "research_output", "strict": True, "schema": candidates._PassageExtraction.model_json_schema()}},
                "max_input_utf8_bytes_per_request": 60000, "budget_cny": 1,
                "conservative_batch_estimate_cny": 0.446,
                "price_source": "https://help.aliyun.com/zh/model-studio/qwen3-7-flash",
                "price_note": "Beijing <=256K tier: input 0.6 and output 2.4 CNY/million tokens, conservative 60000 input tokens including schema and 8192 output tokens per request. Thinking disabled. This is a bounded request estimate, not an account billing cap.",
                "limitations": ["No private data, full papers, model training or production database writes", "Six synthetic passages and two short abstract excerpts; not full-paper accuracy, independent human gold or user effectiveness"],
                "requests": requests}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"manifest": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "requests": len(requests)}, ensure_ascii=False))


def run(path, approved_hash, output):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not approved_hash or digest != approved_hash:
        raise ValueError("Exact manifest hash approval is required")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["model"] != MODEL or manifest["endpoint"] != "https://dashscope.aliyuncs.com/compatible-mode/v1" or len(manifest["requests"]) != 8:
        raise ValueError("Unsupported request manifest")
    expected_format = {"type": "json_schema", "json_schema": {"name": "research_output", "strict": True, "schema": candidates._PassageExtraction.model_json_schema()}}
    if manifest.get("response_format") != expected_format or manifest["max_output_tokens"] != 8192:
        raise ValueError("Manifest schema or output limit differs from this runner")
    settings = Settings(_env_file=ROOT / ".env", access_mode="local", offline_mode=False,
                        research_model_enabled=True, llm_model=manifest["model"], llm_api_base=manifest["endpoint"],
                        research_model_max_requests=8, research_model_max_output_tokens=8192,
                        research_model_max_input_chars=60000, research_model_timeout_seconds=60,
                        research_model_enable_thinking=False, research_model_response_format="json_schema",
                        research_model_schema_require_all=False)
    if not settings.dashscope_api_key.strip():
        raise ValueError("DASHSCOPE_API_KEY is not configured in this process; no requests sent")
    output.mkdir(parents=True, exist_ok=True)
    ledger = path.with_suffix(".executed.json")
    with ledger.open("x", encoding="utf-8") as handle:
        json.dump({"sha256": digest, "started_at": datetime.now(UTC).isoformat(), "no_automatic_replay": True}, handle)
    model_runtime.get_settings = lambda: settings
    results = []

    class UsageLog(logging.Handler):
        def emit(self, record):
            with (output / "transport.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(record.getMessage() + "\n")

    model_runtime.logger.addHandler(UsageLog())
    with model_runtime.model_call_scope(f"approved-{digest[:12]}"):
        for request in manifest["requests"]:
            result = {"id": request["id"], "scope": request["scope"], "source_url": request["source_url"]}

            def approved_chat(messages, json_mode=False):
                if messages != request["messages"] or len(json.dumps(messages, ensure_ascii=False).encode()) > 60000:
                    raise ValueError("Outbound input differs from approved manifest")
                if len(json.dumps({"messages": messages, "response_format": expected_format}, ensure_ascii=False).encode()) > 60000:
                    raise ValueError("Messages plus schema exceed approved input budget")
                raw = model_runtime.structured_chat(messages, schema=candidates._PassageExtraction.model_json_schema(), prompt_version=candidates.PROMPT_VERSION, schema_version=candidates.SCHEMA_VERSION)
                result["raw_output"] = raw
                return raw

            candidates.chat = approved_chat
            try:
                bundle = candidates.extract_candidates(ExtractionInput.model_validate(request["input"]))
                result.update(status="candidate_output", bundle=bundle.model_dump(mode="json"))
            except Exception as exc:
                result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
            results.append(result)
            (output / "outputs.json").write_text(json.dumps({"manifest_sha256": digest, "results": results, "human_reviewed": False}, ensure_ascii=False, indent=2), encoding="utf-8")
            if result["status"] == "failed" and result.get("error_type") == "ResearchModelError":
                break
    print(json.dumps({"output": str(output), "processed": len(results), "human_reviewed": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approved-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.manifest)
    elif args.output is None:
        parser.error("run requires --output")
    else:
        run(args.manifest, args.approved_sha256, args.output)
