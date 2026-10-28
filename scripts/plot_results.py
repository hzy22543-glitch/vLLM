"""Plot validated summaries; labels reflect the actual sample count."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

def plot_load_reports(report_dir, output_dir):
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8))
    for row, section, labels in ((0, "baseline", ["1 req/s, C1", "Unlimited rate, C1"]),
                                (1, "concurrency", ["C32", "C64", "C128"])):
        with (report_dir / f"{section}-summary.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        x = list(range(len(rows)))
        means = [float(r["throughput_run_mean"]) for r in rows]
        deviations = [float(r["throughput_run_sd"]) for r in rows]
        bars = axes[row,0].bar(x, means, yerr=deviations, capsize=5, color="#237f8c", width=.55)
        axes[row,0].bar_label(bars, fmt="%.1f", padding=6)
        axes[row,0].set_ylim(0, max(a+b for a,b in zip(means,deviations))*1.25)
        axes[row,0].set_ylabel("Output tokens/s (run mean +/- SD)")
        latencies=[float(r["p95_e2el_ms"])/1000 for r in rows]
        bars=axes[row,1].bar(x,latencies,color="#cf8651",width=.55)
        axes[row,1].bar_label(bars,fmt="%.2f",padding=5)
        axes[row,1].set_ylim(0,max(latencies)*1.25)
        axes[row,1].set_ylabel("Pooled P95 E2EL (seconds)")
        for ax in axes[row]:
            ax.set_xticks(x,labels)
            ax.set_title("Baseline: 3 x 200 requests/condition" if row==0 else
                         "Concurrency: 3 x 512 requests/condition (7-15 s/run)",fontsize=10)
            ax.spines[["top","right"]].set_visible(False)
            ax.grid(axis="y",alpha=.15);ax.set_axisbelow(True)
    fig.suptitle("Single-GPU inference: baseline and finite-batch concurrency",fontsize=14)
    fig.text(.5,.014,"159-161 input / 64 output tokens | APC OFF | E2EL excludes client queue | SD is not a confidence interval",
             ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.96))
    fig.savefig(output_dir/"load-overview.png",dpi=170)
    plt.close(fig)
    print(output_dir/"load-overview.png")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "reports/prefix-cache-summary.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/figures")
    parser.add_argument("--load-report-dir", type=Path, help="Optional baseline/concurrency summaries directory")
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
    load_dir = args.load_report_dir or args.summary.parent
    if all((load_dir / f"{name}-summary.csv").exists() for name in ("baseline", "concurrency")):
        plot_load_reports(load_dir, args.output_dir)

if __name__ == "__main__":
    main()
