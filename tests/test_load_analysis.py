import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from audit_load import inspect_load_batch, read_load_run, read_gpu, summarize_load
from analyze_project import analyze


class LoadAnalysisTests(unittest.TestCase):
    def test_all_three_experiments_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=analyze(ROOT/"results",Path(tmp))
            self.assertEqual((report["runs"],report["requests"],report["failed"]),(35,7808,0))
        baseline=inspect_load_batch(ROOT/"results/baseline","baseline")
        self.assertAlmostEqual(summarize_load(baseline,"serial")["output_throughput"],110.3375576927912)

    def assert_mutation_rejected(self,callback):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"c032_run1"
            shutil.copytree(ROOT/"results/concurrency/c032_run1",target)
            callback(target)
            with self.assertRaises(ValueError):
                read_load_run(target,"c032","concurrency")

    def change_manifest(self,path,callback):
        p=path/"manifest.json";m=json.loads(p.read_text());callback(m);p.write_text(json.dumps(m))

    def test_wrong_concurrency_is_rejected(self):
        def change(m):m["command"][m["command"].index("--max-concurrency")+1]="64"
        self.assert_mutation_rejected(lambda p:self.change_manifest(p,change))

    def test_wrong_rate_is_rejected(self):
        def change(m):m["command"][m["command"].index("--request-rate")+1]="1"
        self.assert_mutation_rejected(lambda p:self.change_manifest(p,change))

    def test_warmup_overflow_is_rejected(self):
        def change(m):m["service_warmup_usage"][0]["prompt_tokens"]=5000
        self.assert_mutation_rejected(lambda p:self.change_manifest(p,change))

    def test_input_tampering_is_rejected(self):
        self.assert_mutation_rejected(lambda p:(p/"dataset.jsonl").write_text("{}\n"))

    def test_gpu_trace_wrong_day_is_rejected(self):
        def change(p):
            f=p/"gpu.csv";f.write_text(f.read_text().replace("2026/10/28","2026/10/29"))
        self.assert_mutation_rejected(change)

    def test_percentiles_are_recomputed(self):
        def change(p):
            f=p/"result.json";d=json.loads(f.read_text());d["p95_e2el_ms"]=1;f.write_text(json.dumps(d))
        self.assert_mutation_rejected(change)

    def test_batch_config_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"baseline"
            shutil.copytree(ROOT/"results/baseline",root)
            def change(m):m["server_config"]["scheduler_config"]["max_num_seqs"]=128
            self.change_manifest(root/"serial_run2",change)
            with self.assertRaisesRegex(ValueError,"drift"):
                inspect_load_batch(root,"baseline")

    def test_missing_gpu_value_stays_unknown(self):
        from datetime import datetime
        original=ROOT/"results/concurrency/c032_run1"
        m=json.loads((original/"manifest.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"gpu.csv"
            lines=(original/"gpu.csv").read_text().splitlines()
            output=[lines[0]]
            for line in lines[1:]:
                row=line.split(",");row[4]=" N/A";output.append(",".join(row))
            path.write_text("\n".join(output)+"\n")
            report=read_gpu(path,datetime.fromisoformat(m["started_utc"]),datetime.fromisoformat(m["finished_utc"]))
            self.assertIsNone(report["power_max"])
            self.assertEqual(report["power_available_samples"],0)


if __name__=="__main__":
    unittest.main()
