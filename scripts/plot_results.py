"""Plot validated summaries; labels reflect the actual sample count."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "reports/summary.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/figures")
    args = parser.parse_args()
    with args.summary.open(encoding="utf-8") as f:
        data = {r["group"]: r for r in csv.DictReader(f)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, prefix, title in zip(axes, ("shared", "independent_cold"), ("Shared prefix (prewarmed)", "Independent prefixes (cold start)")):
        rows = [data[prefix + "_" + mode] for mode in ("off", "on")]
        bars = ax.bar([0, 1], [float(r["mean_all"]) for r in rows],
                      yerr=[float(r["run_std"]) for r in rows], capsize=5,
                      color=["#63758a", "#168d89"], width=.58)
        ax.bar_label(bars, fmt="%.2f", padding=7)
        ax.set_xticks([0, 1], ["APC OFF", "APC ON"])
        ax.set(title=title, ylabel="Mean TTFT (ms)", ylim=(0, 130))
        ax.set_ylim(0, max(float(r["mean_all"])+float(r["run_std"]) for r in rows) * 1.25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
        counts = " / ".join(f"{mode}: {r['runs']} runs, {r['requests']} requests" for mode, r in zip(("OFF", "ON"), rows))
        ax.set_xlabel(counts, fontsize=9, labelpad=12)
    fig.suptitle("vLLM prefix caching: all measured requests retained", fontsize=14)
    fig.text(.5, .015, "Error bars: sample standard deviation of run means (not confidence intervals)", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .96))
    fig.savefig(args.output_dir / "prefix-cache-ttft.png", dpi=180)
    plt.close(fig)
    print(args.output_dir / "prefix-cache-ttft.png")

if __name__ == "__main__":
    main()
