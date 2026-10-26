"""Compatibility entry point for the validated APC batch analysis."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_results import inspect_batch, export

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=ROOT / "results/prefix-cache")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--requests", type=int, default=100)
    args = parser.parse_args()
    if args.runs < 1 or args.requests < 1:
        parser.error("runs and requests must be positive")
    summaries = export(inspect_batch(args.result_dir, args.runs, args.requests), args.output_dir)
    for row in summaries:
        print(f"{row['group']}: runs={row['runs']}, N={row['requests']}, TTFT={row['mean_all']:.3f} ms")

if __name__ == "__main__":
    main()
