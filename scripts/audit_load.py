"""Validate fixed baseline/concurrency protocols and summarize all requests (stdlib only)."""
import argparse
import hashlib
import json
import math
import statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path

from audit_prefix_cache import ROOT, counter, load_json, percentile, require, sd, validate, write_csv

PROTOCOLS = {
    "baseline": {"low_rate": (1, "1", 200), "serial": (1, "inf", 200)},
    "concurrency": {"c032": (32, "inf", 512), "c064": (64, "inf", 512), "c128": (128, "inf", 512)},
}
LOCAL_TZ = timezone(timedelta(hours=8))


def option(command, flag):
    require(command.count(flag) == 1, f"Missing/duplicate option: {flag}")
    i = command.index(flag)
    require(i + 1 < len(command), f"Missing value: {flag}")
    return command[i + 1]


def read_gpu(path, started, finished):
    """GPU trace uses explicit UTC+08; summarize runner window, including warmups."""
    import csv
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, skipinitialspace=True))
    require(bool(rows), f"{path}: empty GPU trace")
    samples = []
    columns = {"utilization": "utilization.gpu [%]", "memory": "memory.used [MiB]",
               "power": "power.draw [W]", "temperature": "temperature.gpu",
               "clock": "clocks.current.sm [MHz]"}
    for row in rows:
        require(row.get("index", "").strip() == "0", f"{path}: expected GPU 0")
        stamp = datetime.strptime(row["timestamp"], "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=LOCAL_TZ)
        values = {}
        for name, key in columns.items():
            raw = row[key].strip()
            if raw in {"N/A", "[N/A]", "Not Supported", "[Not Supported]"}:
                values[name] = None
            else:
                value = float(raw.split()[0])
                require(math.isfinite(value) and value >= 0, f"{path}: invalid GPU reading")
                values[name] = value
        samples.append((stamp, values))
    require(all(a[0] < b[0] for a, b in zip(samples, samples[1:])), f"{path}: unordered GPU timestamps")
    require(samples[0][0] <= started and samples[-1][0] >= finished, f"{path}: GPU trace does not cover runner window")
    selected = [v for t, v in samples if started <= t <= finished]
    require(bool(selected), f"{path}: no overlapping GPU samples")
    summary = {"gpu_window": "runner_including_warmup", "gpu_samples": len(selected),
               "gpu_max_gap_s": max(((b[0]-a[0]).total_seconds() for a,b in zip(samples,samples[1:])), default=0)}
    for name in columns:
        values = [v[name] for v in selected if v[name] is not None]
        summary[name + "_max"] = max(values) if values else None
        summary[name + "_min"] = min(values) if values else None
        summary[name + "_available_samples"] = len(values)
    return summary


def read_load_run(path, group, section):
    concurrency, rate, count = PROTOCOLS[section][group]
    for name in ("manifest.json", "result.json", "dataset.jsonl", "benchmark.log", "metrics_before.txt", "metrics_after.txt"):
        require((path / name).is_file(), f"{path}: missing {name}")
    m, d = load_json(path / "manifest.json"), load_json(path / "result.json")
    require(m.get("status") == "completed", f"{path}: incomplete manifest")
    require(not (errors := validate(d)), f"{path}: {errors}")
    require(d["num_prompts"] == count, f"{path}: wrong request count")
    raw = (path / "dataset.jsonl").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == m["dataset_sha256"], f"{path}: input SHA256 mismatch")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    require(len(rows) == count and all(isinstance(row.get("prompt"), str) and row["prompt"] for row in rows),
            f"{path}: invalid input rows")
    require(d["output_lens"] == [row["output_tokens"] for row in rows] == [64] * count, f"{path}: output length mismatch")
    config, command = m["server_config"], m["command"]
    require(m["apc_expected"] == "off" and m["cache_state"] == "cold" and
            config["cache_config"]["enable_prefix_caching"] is False, f"{path}: APC/cold state mismatch")
    require(not m.get("prefix_warmup_usage") and m.get("cache_reset_success") is None, f"{path}: unexpected cache prefill/reset")
    require(m.get("warmups") == 3 and len(m.get("service_warmup_usage", [])) == 3, f"{path}: missing warmup")
    limit = config["model_config"]["max_model_len"]
    for usage in m["service_warmup_usage"]:
        require(usage["completion_tokens"] == 64 and 0 < usage["prompt_tokens"] <= limit - 64 and
                usage["total_tokens"] == usage["prompt_tokens"] + 64, f"{path}: invalid warmup usage")
    require(all(0 < a <= limit - b for a, b in zip(d["input_lens"], d["output_lens"])), f"{path}: input context overflow")
    for flag in ("--skip-chat-template", "--disable-shuffle", "--no-oversample", "--ignore-eos", "--save-detailed"):
        require(command.count(flag) == 1, f"{path}: missing/duplicate {flag}")
    expected = {"--custom-output-len": "-1", "--temperature": "0", "--num-warmups": "0",
                "--ready-check-timeout-sec": "0", "--max-concurrency": str(concurrency),
                "--request-rate": rate, "--seed": "42", "--num-prompts": str(count),
                "--backend": "openai-chat", "--endpoint": "/v1/chat/completions",
                "--model": config["model_config"]["model"], "--tokenizer": config["model_config"]["model"]}
    for flag, value in expected.items():
        require(option(command, flag) == value, f"{path}: wrong {flag}")
    actual_rate = float(d["request_rate"])
    require(d["max_concurrency"] == concurrency and actual_rate == float(rate), f"{path}: load mismatch")
    require(d["model_id"] == config["model_config"]["model"], f"{path}: model mismatch")
    for q in (50, 95, 99):
        require(math.isclose(percentile(d["latencies"], q)*1000, d[f"p{q}_e2el_ms"], rel_tol=1e-6),
                f"{path}: E2EL percentile mismatch")
    started, finished = [datetime.fromisoformat(m[key]) for key in ("started_utc", "finished_utc")]
    require(started.tzinfo is not None and finished.tzinfo is not None and started < finished, f"{path}: invalid times")
    require(d["duration"] <= (finished-started).total_seconds(), f"{path}: benchmark exceeds runner window")
    preemptions = counter(path / "metrics_after.txt", "vllm:num_preemptions_total") - counter(path / "metrics_before.txt", "vllm:num_preemptions_total")
    require(preemptions >= 0, f"{path}: preemption counter reset")
    for metric in ("queries", "hits"):
        delta = counter(path / "metrics_after.txt", f"vllm:prefix_cache_{metric}_total") - counter(path / "metrics_before.txt", f"vllm:prefix_cache_{metric}_total")
        require(delta == 0, f"{path}: unexpected APC activity while OFF")
    gpu = read_gpu(path / "gpu.csv", started, finished) if section == "concurrency" else {}
    return {"path": path, "group": group, "section": section, "manifest": m, "result": d, "sha256": digest,
            "preemptions_delta": preemptions, "gpu": gpu}


def inspect_load_batch(root, section):
    require(section in PROTOCOLS, f"Unknown section: {section}")
    expected = {f"{group}_run{i}" for group in PROTOCOLS[section] for i in range(1, 4)}
    actual = {p.name for p in root.iterdir() if p.is_dir()}
    require(actual == expected, f"{section}: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    records = [read_load_run(root / f"{g}_run{i}", g, section) for g in PROTOCOLS[section] for i in range(1, 4)]
    require(len({r["sha256"] for r in records}) == 1, f"{section}: inputs differ")
    require(len({tuple(r["result"]["input_lens"]) for r in records}) == 1, f"{section}: input tokenization differs")
    require(len({json.dumps({"config":r["manifest"]["server_config"],"versions":r["manifest"]["versions"]},sort_keys=True)
                 for r in records}) == 1, f"{section}: configuration/version drift")
    chronological = sorted(records, key=lambda r: r["manifest"]["started_utc"])
    for a,b in zip(chronological, chronological[1:]):
        require(a["manifest"]["finished_utc"] <= b["manifest"]["started_utc"], f"{section}: overlapping runs")
    return records


def summarize_load(records, group):
    ds = [r["result"] for r in records if r["group"] == group]
    ttfts = [1000*x for d in ds for x in d["ttfts"]]
    latencies = [1000*x for d in ds for x in d["latencies"]]
    arrivals = [1000*(q+lat) for d in ds for q,lat in zip(d["queue_times"],d["latencies"])]
    throughput = [d["output_throughput"] for d in ds]
    return {"group":group, "runs":len(ds), "requests":sum(d["completed"] for d in ds),
            "input_min":min(min(d["input_lens"]) for d in ds), "input_max":max(max(d["input_lens"]) for d in ds),
            "duration_min_s":min(d["duration"] for d in ds), "duration_max_s":max(d["duration"] for d in ds),
            "output_throughput":sum(d["total_output_tokens"] for d in ds)/sum(d["duration"] for d in ds),
            "throughput_run_mean":st.mean(throughput), "throughput_run_sd":sd(throughput),
            "throughput_range_pct":(max(throughput)/min(throughput)-1)*100,
            "mean_ttft_ms":st.mean(ttfts), "ttft_run_sd_ms":sd([d["mean_ttft_ms"] for d in ds]),
            "mean_tpot_ms":st.mean(d["mean_tpot_ms"] for d in ds),
            "p95_e2el_ms":percentile(latencies,95), "p95_arrival_ms":percentile(arrivals,95)}


def export_load(records, out, section):
    summaries = [summarize_load(records,g) for g in PROTOCOLS[section]]
    write_csv(out / f"{section}-summary.csv", summaries)
    rows, telemetry = [], []
    for r in sorted(records, key=lambda x:x["manifest"]["started_utc"]):
        d,m = r["result"],r["manifest"]
        row={"run":r["path"].name, "started_utc":m["started_utc"], "finished_utc":m["finished_utc"],
             "dataset_sha256":r["sha256"],"input_min":min(d["input_lens"]),"input_max":max(d["input_lens"])}
        for key in ("completed","failed","duration","max_concurrency","request_rate","mean_ttft_ms","mean_tpot_ms","p95_e2el_ms","output_throughput"):
            row[key]=d[key]
        row["p95_arrival_ms"]=percentile([1000*(q+lat) for q,lat in zip(d["queue_times"],d["latencies"])],95)
        row["preemptions_delta"]=r["preemptions_delta"]
        rows.append(row)
        if r["gpu"]:telemetry.append({"run":r["path"].name,**r["gpu"]})
    write_csv(out/f"{section}-runs.csv",rows)
    if telemetry:write_csv(out/f"{section}-gpu.csv",telemetry)
    lines=[f"# {section} 自动复算", "",f"通过：{len(records)} 轮、{sum(r['result']['completed'] for r in records)} 条请求，0 失败。",
           "", "| 条件 | 总输出 tokens / 总时间 (tokens/s) | TTFT 均值 (ms) | TPOT 均值 (ms) | 合并 P95 E2EL (ms) | 测量时间范围 (s) |",
           "|---|---:|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['group']} | {s['output_throughput']:.2f} | {s['mean_ttft_ms']:.2f} | {s['mean_tpot_ms']:.2f} | {s['p95_e2el_ms']:.2f} | {s['duration_min_s']:.2f}–{s['duration_max_s']:.2f} |")
    lines += ["", "保留所有请求；分位数从合并后的逐请求数据计算，不对分位数取平均。轮间 SD 不是置信区间。",
              "request_rate=inf 下到达至完成包含客户端批量积压，不代表在线稳定到达场景的用户延迟。",
              "GPU 汇总窗口是整个 runner（含预热），不是精确 benchmark 窗口。N/A 保留为空值。"]
    (out/f"{section}-computed.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--section",choices=PROTOCOLS,required=True)
    p.add_argument("--results-dir",type=Path)
    p.add_argument("--output-dir",type=Path,default=ROOT/"reports")
    args=p.parse_args()
    records=inspect_load_batch(args.results_dir or ROOT/"results"/args.section,args.section)
    export_load(records,args.output_dir,args.section)
    print(f"PASS: {args.section}, {len(records)} runs")


if __name__ == "__main__":
    main()
