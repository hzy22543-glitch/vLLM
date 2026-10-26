"""Validate complete APC runs before producing reproducible summaries (stdlib only)."""
import argparse
import csv
import hashlib
import json
import math
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("shared_off", "shared_on", "independent_cold_off", "independent_cold_on")


def load_json(path):
    def reject(value):
        raise ValueError(f"{path}: non-finite JSON value {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q / 100
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def sd(values):
    return st.stdev(values) if len(values) > 1 else 0.0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(d):
    """Return arithmetic/shape errors; absent request details are not accepted."""
    problems = []
    n = d.get("num_prompts")
    if not isinstance(n, int) or n <= 0:
        return ["num_prompts must be a positive integer"]
    if d.get("completed", 0) + d.get("failed", 0) != n:
        problems.append("completed + failed != num_prompts")
    for key in ("ttfts", "latencies", "input_lens", "output_lens", "queue_times", "errors"):
        values = d.get(key)
        if not isinstance(values, list) or len(values) != n:
            problems.append(f"{key}: missing or length != num_prompts")
        elif key != "errors" and any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
            problems.append(f"{key}: invalid number")
    if problems:
        return problems
    for key, total in (("input_lens", "total_input_tokens"), ("output_lens", "total_output_tokens")):
        if sum(d[key]) != d.get(total):
            problems.append(f"{key}: sum != {total}")
    if d.get("failed") != 0 or d.get("completed") != n or any(d["errors"]):
        problems.append("run contains failed requests")
    duration = d.get("duration", 0)
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        problems.append("duration must be finite and positive")
    else:
        expected = d["total_output_tokens"] / duration
        if not math.isclose(expected, d.get("output_throughput", -1), rel_tol=1e-6):
            problems.append("output_throughput != output tokens / duration")
    if any(lat < ttft for lat, ttft in zip(d["latencies"], d["ttfts"])):
        problems.append("latency < TTFT")
    expected_metrics = {
        "mean_ttft_ms": st.mean(d["ttfts"]) * 1000,
        "mean_e2el_ms": st.mean(d["latencies"]) * 1000,
        "p50_ttft_ms": percentile(d["ttfts"], 50) * 1000,
        "p95_ttft_ms": percentile(d["ttfts"], 95) * 1000,
    }
    if all(length > 1 for length in d["output_lens"]):
        expected_metrics["mean_tpot_ms"] = st.mean(
            (lat - ttft) * 1000 / (length - 1)
            for lat, ttft, length in zip(d["latencies"], d["ttfts"], d["output_lens"])
        )
    for key, expected in expected_metrics.items():
        actual = d.get(key)
        if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-4):
            problems.append(f"{key}: differs from per-request data")
    return problems


def counter(path, name):
    # Match the exact metric; never include external_prefix_cache_*.
    pattern = re.compile(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+([^\s]+)")
    values = [float(m.group(1)) for line in path.read_text(encoding="utf-8").splitlines()
              if (m := pattern.match(line))]
    require(bool(values) and all(math.isfinite(v) for v in values), f"{path}: missing/invalid {name}")
    return sum(values)


def read_run(path, group, requests):
    m = load_json(path / "manifest.json")
    d = load_json(path / "result.json")
    require(m.get("status") == "completed", f"{path}: manifest is not completed")
    require(not (issues := validate(d)), f"{path}: {issues}")
    require(d["num_prompts"] == requests, f"{path}: expected {requests} requests")
    raw = (path / "dataset.jsonl").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == m["dataset_sha256"], f"{path}: input SHA256 mismatch")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    require(len(rows) == requests, f"{path}: input row count mismatch")
    require(d["output_lens"] == [r["output_tokens"] for r in rows], f"{path}: actual output length mismatch")
    require(all(x == 64 for x in d["output_lens"]), f"{path}: this protocol requires 64-token output")
    mode = group.rsplit("_", 1)[1]
    state = "hot" if group.startswith("shared") else "cold"
    require(m["apc_expected"] == mode and m["cache_state"] == state, f"{path}: mislabeled condition")
    config = m["server_config"]
    require(config["cache_config"]["enable_prefix_caching"] is (mode == "on"), f"{path}: APC mismatch")
    if mode == "on":
        require(m.get("cache_reset_success") is True, f"{path}: cache reset unverified")
    require(m.get("warmups") == 3 and len(m.get("service_warmup_usage", [])) == 3, f"{path}: missing warmups")
    require(bool(m.get("prefix_warmup_usage")) == (state == "hot"), f"{path}: prefix warmup mismatch")
    limit = config["model_config"]["max_model_len"]
    require(all(a + b <= limit for a, b in zip(d["input_lens"], d["output_lens"])), f"{path}: context overflow")
    cmd = m["command"]
    for flag in ("--skip-chat-template", "--disable-shuffle", "--no-oversample", "--ignore-eos", "--save-detailed"):
        require(flag in cmd, f"{path}: missing {flag}")
    for flag, value in {"--custom-output-len": "-1", "--temperature": "0", "--num-warmups": "0",
                        "--ready-check-timeout-sec": "0", "--max-concurrency": "1",
                        "--request-rate": "inf", "--seed": "42", "--num-prompts": str(requests)}.items():
        require(flag in cmd and cmd.index(flag) + 1 < len(cmd) and cmd[cmd.index(flag) + 1] == value,
                f"{path}: wrong {flag}")
    require(d["max_concurrency"] == 1 and str(d["request_rate"]) == "inf", f"{path}: load mismatch")
    require(d["model_id"] == config["model_config"]["model"], f"{path}: model mismatch")
    for file in ("benchmark.log", "metrics_before.txt", "metrics_after.txt"):
        require((path / file).is_file(), f"{path}: missing {file}")
    deltas = {}
    for key in ("queries", "hits"):
        name = f"vllm:prefix_cache_{key}_total"
        deltas[key] = counter(path / "metrics_after.txt", name) - counter(path / "metrics_before.txt", name)
    require(0 <= deltas["hits"] <= deltas["queries"], f"{path}: invalid/reset metrics counters")
    window_matches = deltas["queries"] == d["total_input_tokens"]
    rate = deltas["hits"] / deltas["queries"] if mode == "on" and window_matches else None
    return {"path": path, "group": group, "manifest": m, "result": d, "sha256": digest,
            "queries_delta": deltas["queries"], "hits_delta": deltas["hits"],
            "cache_window_matches": window_matches, "cache_hit_ratio": rate}


def inspect_batch(root, runs=5, requests=100):
    expected = {f"{g}_run{i}" for g in GROUPS for i in range(1, runs + 1)}
    actual = {p.name for p in root.iterdir() if p.is_dir() and p.name != "figures"}
    require(actual == expected, f"Batch directories: missing={sorted(expected-actual)}, unexpected={sorted(actual-expected)}")
    records = [read_run(root / f"{g}_run{i}", g, requests) for g in GROUPS for i in range(1, runs + 1)]
    conditions = set()
    for record in records:
        config = json.loads(json.dumps(record["manifest"]["server_config"]))
        config["cache_config"].pop("enable_prefix_caching")
        conditions.add(json.dumps({"config": config, "versions": record["manifest"]["versions"]}, sort_keys=True))
    require(len(conditions) == 1, "Versions/server configuration differ beyond APC")
    for prefix in ("shared", "independent_cold"):
        subset = [r for r in records if r["group"].startswith(prefix)]
        require(len({r["sha256"] for r in subset}) == 1, f"{prefix}: inputs differ across modes or rounds")
        require(len({tuple(r["result"]["input_lens"]) for r in subset}) == 1, f"{prefix}: token lengths differ")
    return records


def summarize(records, name):
    ds = [r["result"] for r in records if r["group"] == name]
    require(bool(ds), f"No runs for {name}")
    times = [[t * 1000 for t in d["ttfts"]] for d in ds]
    all_times = [t for run in times for t in run]
    rest = [t for run in times for t in run[1:]]
    return dict(group=name, runs=len(ds), requests=len(all_times),
                mean_all=st.mean(all_times), run_std=sd([st.mean(t) for t in times]),
                mean_first=st.mean(t[0] for t in times), mean_rest=st.mean(rest) if rest else 0,
                rest_run_std=sd([st.mean(t[1:]) for t in times if len(t) > 1]),
                p50_all=percentile(all_times, 50), p95_all=percentile(all_times, 95),
                mean_tpot_ms=st.mean(d["mean_tpot_ms"] for d in ds),
                mean_e2el_ms=st.mean(d["mean_e2el_ms"] for d in ds),
                output_throughput=sum(d["total_output_tokens"] for d in ds) / sum(d["duration"] for d in ds))


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(records, out):
    summaries = [summarize(records, g) for g in GROUPS]
    write_csv(out / "summary.csv", summaries)
    rows = []
    for record in records:
        d, m = record["result"], record["manifest"]
        row = {"run": record["path"].name, "started_utc": m["started_utc"], "dataset_sha256": record["sha256"]}
        for k in ("num_prompts", "completed", "failed", "total_input_tokens", "total_output_tokens",
                  "duration", "mean_ttft_ms", "p95_ttft_ms", "mean_tpot_ms", "mean_e2el_ms", "output_throughput"):
            row[k] = d[k]
        row["p95_arrival_to_completion_ms"] = percentile([(q + lat) * 1000 for q, lat in zip(d["queue_times"], d["latencies"])], 95)
        for k in ("queries_delta", "hits_delta", "cache_window_matches", "cache_hit_ratio"):
            row[k] = record[k]
        rows.append(row)
    write_csv(out / "runs.csv", rows)
    lines = ["# 正式实验自动复算", "", f"验证通过：{len(records)} 轮，{sum(r['result']['completed'] for r in records)} 条成功请求，0 失败。", "",
             "| 条件 | 轮数 | 请求数 | TTFT 均值 ± 轮间 SD (ms) | TPOT (ms) | 输出 tokens/s |",
             "|---|---:|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['group']} | {s['runs']} | {s['requests']} | {s['mean_all']:.3f} ± {s['run_std']:.3f} | {s['mean_tpot_ms']:.3f} | {s['output_throughput']:.3f} |")
    for prefix in ("shared", "independent_cold"):
        off, on = [next(s for s in summaries if s["group"] == prefix + "_" + mode) for mode in ("off", "on")]
        lines += ["", f"{prefix} TTFT 降低率：(OFF−ON)/OFF = {(off['mean_all']-on['mean_all'])/off['mean_all']*100:.3f}%。"]
    lines += ["", "全部正式请求都保留。误差为轮均值的样本标准差，不是置信区间；吞吐按总输出 tokens / 总测量时间计算。",
              "命中率仅在 ON 且计数增量与测量输入总数相符时计算；OFF 的零分母不解释为 0% 命中。",
              "详细逐轮值、输入 SHA256、计数增量及客户端排队后的延迟见 runs.csv。"]
    (out / "computed.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results/prefix-cache")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--requests", type=int, default=100)
    args = parser.parse_args()
    if args.runs < 1 or args.requests < 1:
        parser.error("--runs and --requests must be positive")
    records = inspect_batch(args.results_dir, args.runs, args.requests)
    summaries = export(records, args.output_dir)
    for s in summaries:
        print(f"{s['group']}: {s['runs']} runs, {s['requests']} requests, TTFT={s['mean_all']:.3f} ms")
    print(f"PASS: {len(records)} runs validated. Report: {args.output_dir / 'computed.md'}")


if __name__ == "__main__":
    main()
