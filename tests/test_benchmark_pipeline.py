import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts")]
from audit_results import percentile, validate, read_run, inspect_batch, summarize, counter
from build_workload import common_prefix_len, get_token_ids
from prepare_dataset import convert_dataset
from run_benchmark import command, reset_cache, warmup_prompt, request_json

FIXTURE = ROOT / "results/prefix-cache/shared_on_run1"


class AnalysisTests(unittest.TestCase):
    def test_percentile_interpolation(self):
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 95), 3.85)
        self.assertIsNone(percentile([], 95))

    def test_archived_batch_validates_all_requests(self):
        records = inspect_batch(ROOT / "results/prefix-cache")
        self.assertEqual(len(records), 20)
        for name in ("shared_on", "independent_cold_on"):
            row = summarize(records, name)
            self.assertEqual(row["requests"], 500)
            self.assertEqual(row["runs"], 5)
        self.assertAlmostEqual(summarize(records, "shared_on")["mean_all"], 19.526460121987838)
        self.assertTrue(all(r["cache_window_matches"] for r in records if r["group"].endswith("_on")))

    def test_totals_and_missing_details_are_rejected(self):
        original = json.loads((FIXTURE / "result.json").read_text())
        self.assertEqual(validate(original), [])
        for change in ("total_output_tokens", "ttfts"):
            d = copy.deepcopy(original)
            if change == "ttfts":
                del d[change]
            else:
                d[change] += 1
            self.assertTrue(validate(d))

    def test_nonfinite_timing_is_rejected(self):
        d = json.loads((FIXTURE / "result.json").read_text())
        d["ttfts"][0] = float("nan")
        self.assertTrue(validate(d))

    def mutate_fixture(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            shutil.copytree(FIXTURE, target)
            callback(target)
            with self.assertRaises(ValueError):
                read_run(target, "shared_on", 100)

    def test_failed_manifest_is_rejected_even_if_requests_succeeded(self):
        def mutate(path):
            p = path / "manifest.json"
            d = json.loads(p.read_text()); d["status"] = "failed"; p.write_text(json.dumps(d))
        self.mutate_fixture(mutate)

    def test_tampered_dataset_is_rejected(self):
        self.mutate_fixture(lambda p: (p / "dataset.jsonl").write_text("changed\n"))

    def test_unverified_reset_is_rejected(self):
        def mutate(path):
            p = path / "manifest.json"
            d = json.loads(p.read_text()); d["cache_reset_success"] = False; p.write_text(json.dumps(d))
        self.mutate_fixture(mutate)

    def test_retry_directory_cannot_silently_enter_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared_on_run1_retry").mkdir()
            with self.assertRaisesRegex(ValueError, "unexpected"):
                inspect_batch(root)

    def test_only_exact_prefix_metric_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "metrics.txt"
            p.write_text('vllm:prefix_cache_hits_total{engine="0"} 4\nvllm:external_prefix_cache_hits_total{engine="0"} 99\n')
            self.assertEqual(counter(p, "vllm:prefix_cache_hits_total"), 4)

    def test_converter_preserves_lengths_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source.jsonl", Path(tmp) / "bench.jsonl"
            source.write_text(json.dumps({"prompt": "a", "max_tokens": 256}) + "\n")
            convert_dataset(source, target)
            self.assertEqual(json.loads(target.read_text())["output_tokens"], 256)
            with self.assertRaises(FileExistsError):
                convert_dataset(source, target)

    def test_tokenizer_return_types(self):
        class Tokenizer:
            def __init__(self, value): self.value = value
            def apply_chat_template(self, *args, **kwargs): return self.value
        for value in ([1, 2], {"input_ids": [1, 2]}):
            self.assertEqual(get_token_ids(Tokenizer(value), "text"), [1, 2])
        self.assertEqual(common_prefix_len([1, 2], [1, 3]), 1)

    def test_warmup_budget_includes_template_and_output(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return {"input_ids": [1] * (36 + 2 * messages[0]["content"].count(" warmup"))}
        tokenizer = Tokenizer()
        for limit in (4096, 512):
            prompt = warmup_prompt(tokenizer, 0, limit)
            ids = get_token_ids(tokenizer, prompt)
            self.assertLessEqual(len(ids) + 64, limit)
            self.assertLessEqual(len(ids), 2048)

    def test_too_small_warmup_context_rejected(self):
        class Tokenizer:
            def apply_chat_template(self, *args, **kwargs): return [1] * 100
        with self.assertRaises(ValueError):
            warmup_prompt(Tokenizer(), 0, 64)

    def test_http_error_includes_server_response(self):
        error = urllib.error.HTTPError("http://localhost/test", 400, "Bad Request", {}, io.BytesIO(b'context length exceeded'))
        with patch("run_benchmark.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaisesRegex(RuntimeError, "context length exceeded"):
                request_json("http://localhost", "/test", {})

    def test_failed_reset_stops_measurement(self):
        with patch("run_benchmark.request_json", return_value={"success": False}):
            with self.assertRaises(RuntimeError):
                reset_cache("http://localhost")
        with patch("run_benchmark.request_json", return_value={"success": True}):
            reset_cache("http://localhost")

    def test_cli_uses_dataset_output_length_and_no_hidden_warmup(self):
        args = SimpleNamespace(base_url="http://localhost", model="model", concurrency=1, request_rate="inf", seed=42)
        cmd = command(args, Path("data.jsonl"), 100, Path("out"))
        self.assertEqual(cmd[cmd.index("--custom-output-len") + 1], "-1")
        for flag in ("--skip-chat-template", "--ignore-eos", "--no-oversample", "--disable-shuffle"):
            self.assertIn(flag, cmd)
        for flag in ("--num-warmups", "--ready-check-timeout-sec"):
            self.assertEqual(cmd[cmd.index(flag) + 1], "0")


if __name__ == "__main__":
    unittest.main()
