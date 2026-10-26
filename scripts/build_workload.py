"""Generate reproducible shared/independent inputs and verify chat token prefixes."""
import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

def common_prefix_len(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))

def get_token_ids(tokenizer, prompt):
    result = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}], tokenize=True, add_generation_prompt=True
    )
    return result["input_ids"] if isinstance(result, Mapping) else result

def make_prompt(doc_id, question_id, repeat=50):
    line = (
        f"文档编号 {doc_id:03d}："
        "本项目研究大语言模型推理服务的请求调度、KV缓存管理、吞吐量和首次Token延迟。"
        "实验目标是分析系统性能变化。\n"
    )
    return line * repeat + f"\n问题：请解释第{question_id}项性能指标。"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Local model/tokenizer directory")
    parser.add_argument("--num-requests", type=int, default=100)
    parser.add_argument("--repeat", type=int, default=50)
    parser.add_argument("--output-tokens", type=int, default=64)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.num_requests < 2 or min(args.repeat, args.output_tokens) <= 0:
        parser.error("Need >=2 requests, positive repeat and output-tokens")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    # A new directory prevents overwriting historical datasets and manifests.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"model": args.model, "requests": args.num_requests, "output_tokens": args.output_tokens,
                "token_scope": "one server-side user chat template", "groups": {}}
    for name in ("shared", "independent"):
        records, ids = [], []
        for i in range(args.num_requests):
            prompt = make_prompt(0 if name == "shared" else i + 1, i + 1, args.repeat)
            tokens = get_token_ids(tokenizer, prompt)
            ids.append(tokens)
            records.append({"id": i, "prompt": prompt, "input_tokens": len(tokens), "max_tokens": args.output_tokens})
        content = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records)
        path = args.output_dir / f"{name}.jsonl"
        path.write_text(content, encoding="utf-8")
        # Adjacent lexical token sequences include the extremal pairwise LCPs.
        ordered = sorted(ids)
        lcps = [common_prefix_len(a, b) for a, b in zip(ordered, ordered[1:])]
        manifest["groups"][name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "input_min": min(map(len, ids)), "input_max": max(map(len, ids)),
            "pairwise_lcp_min": min(lcps), "pairwise_lcp_max": max(lcps),
        }
    (args.output_dir / "workload_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
