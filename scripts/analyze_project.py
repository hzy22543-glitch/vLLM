"""Validate and summarize the complete baseline, concurrency and APC project."""
import argparse
import json
from pathlib import Path
from audit_prefix_cache import ROOT, inspect_batch, export, require
from audit_load import inspect_load_batch, export_load


def analyze(root, out):
    baseline = inspect_load_batch(root / "baseline", "baseline")
    concurrency = inspect_load_batch(root / "concurrency", "concurrency")
    apc = inspect_batch(root / "prefix-cache")
    all_records = baseline + concurrency + apc
    conditions = set()
    for r in all_records:
        config = json.loads(json.dumps(r["manifest"]["server_config"]))
        config["cache_config"].pop("enable_prefix_caching")
        conditions.add(json.dumps({"config": config, "versions":r["manifest"]["versions"]},sort_keys=True))
    require(len(conditions) == 1, "Cross-experiment configuration/version drift")
    for section,records in (("baseline",baseline),("concurrency",concurrency)):
        export_load(records,out,section)
    export(apc,out)
    report = {"runs":len(all_records), "requests":sum(r["result"]["completed"] for r in all_records),
              "failed":0, "sections":{"baseline":len(baseline),"concurrency":len(concurrency),"prefix-cache":len(apc)},
              "scope":"finite-batch measurements; no sustained-load or causal root-cause claim",
              "limitations":["Concurrency measurement windows are under 15 seconds.",
                             "Concurrency runs span two server sessions; run labels are not chronological.",
                             "GPU telemetry covers runner windows including warmups; no client/engine CPU time series.",
                             "Immutable model/tokenizer revisions were not recorded."]}
    (out/"validation.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(f"PASS: {report['runs']} runs, {report['requests']} requests, 0 failures")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir",type=Path,default=ROOT/"results")
    p.add_argument("--output-dir",type=Path,default=ROOT/"reports")
    args=p.parse_args()
    analyze(args.results_dir,args.output_dir)


if __name__=="__main__":
    main()
