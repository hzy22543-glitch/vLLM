"""Convert an explicitly selected workload; preserve requested output length."""
import argparse
import json
from pathlib import Path

def convert_dataset(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError("Source and target must differ")
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("Empty dataset")
    samples = []
    for record in records:
        length = record.get("max_tokens", record.get("output_tokens"))
        if not isinstance(length, int) or length <= 0 or not isinstance(record.get("prompt"), str):
            raise ValueError("Each row needs prompt and positive max_tokens/output_tokens")
        samples.append({"prompt": record["prompt"], "output_tokens": length})
    target.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to silently replace the dataset used by a previous experiment.
    with target.open("x", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    print(f"{source} -> {target}: {len(samples)} requests")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    convert_dataset(args.source, args.target)

if __name__ == "__main__":
    main()
