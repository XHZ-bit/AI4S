"""Offline guard checks; no model requests or production database access."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evaluation.research_atlas.simulated_user_pilot import ROOT, parse_decision, run, validate_input


class SimulatedUserGuardTests(unittest.TestCase):
    def sample(self):
        return {"id": "synthetic-step", "synthetic": True, "persona": "Invented reader",
                "task": "Open a visible control", "observation": {"controls": [
                    {"id": "c1", "action": "click", "role": "button", "name": "Continue"}]}}

    def test_requires_explicit_synthetic_label(self):
        value = self.sample()
        value["synthetic"] = False
        with self.assertRaises(ValueError):
            validate_input(value)

    def test_rejects_duplicate_controls(self):
        value = self.sample()
        value["observation"]["controls"] *= 2
        with self.assertRaises(ValueError):
            validate_input(value)

    def test_rejects_actor_hallucinated_control(self):
        with self.assertRaises(ValueError):
            parse_decision('{"action_id":"hidden-admin"}', validate_input(self.sample()))

    def test_permits_stop_without_inventing_success(self):
        self.assertEqual(parse_decision('{"action_id":"STOP"}', {})["action_id"], "STOP")

    def test_output_length_is_bounded(self):
        with self.assertRaises(ValueError):
            parse_decision(json.dumps({"action_id": "c1", "value": "x" * 201}),
                           validate_input(self.sample()))

    def test_eight_reserved_attempts_block_another_request_before_transport(self):
        with TemporaryDirectory(dir=ROOT / ".tmp", prefix="simulation-guard-") as temporary:
            base = Path(temporary).resolve()
            self.assertTrue(base.is_relative_to((ROOT / ".tmp").resolve()))
            source = base / "input.json"
            source.write_text(json.dumps(self.sample()), encoding="utf-8")
            output = base / "results"
            output.mkdir()
            for index in range(8):
                (output / f"{index}.attempt.json").write_text("{}", encoding="utf-8")
            with patch("app.config.Settings", return_value=SimpleNamespace(
                    dashscope_api_key="synthetic-test-only", tutor_default_api_key="")):
                with self.assertRaisesRegex(ValueError, "request limit"):
                    run(source, output)


if __name__ == "__main__":
    unittest.main()
