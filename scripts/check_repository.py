"""Check full evidence coverage, raw bytes, canonical inputs and Markdown links."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors=[]
    index=json.loads((ROOT/"docs/evidence-sha256.json").read_text(encoding="utf-8"))
    expected={str(p.relative_to(ROOT)) for p in (ROOT/"results").rglob("*") if p.is_file() and p.suffix!=".md"}
    expected.update(str(p.relative_to(ROOT)) for p in (ROOT/"data").iterdir() if p.suffix in {".jsonl",".json"})
    expected.update({"reports/environment.txt","reports/workload_check.json"})
    if set(index)!=expected:
        errors.append(f"Evidence index coverage: missing={sorted(expected-set(index))}, extra={sorted(set(index)-expected)}")
    for relative,digest in index.items():
        p=ROOT/relative
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            errors.append(f"Evidence changed/missing: {relative}")
    for name,run in (("shared","prefix-cache/shared_off_run1"),("independent","prefix-cache/independent_cold_off_run1"),
                     ("baseline","baseline/low_rate_run1"),("concurrency","concurrency/c032_run1")):
        if (ROOT/f"data/{name}.jsonl").read_bytes()!=(ROOT/f"results/{run}/dataset.jsonl").read_bytes():
            errors.append(f"Canonical input differs: {name}")
    provenance=json.loads((ROOT/"docs/evidence-provenance.json").read_text(encoding="utf-8"))
    for relative,record in provenance["files"].items():
        if index.get(relative)!=record["sha256"]:
            errors.append(f"Provenance differs from evidence index: {relative}")
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts or p.is_relative_to(ROOT/"runs"):
            continue
        text=re.sub(r"```.*?```","",p.read_text(encoding="utf-8"),flags=re.S)
        for target in re.findall(r"!?(?:\[[^\]]*\])\(([^)]+)\)",text):
            target=target.strip("<>").split("#",1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (p.parent/target).exists():
                errors.append(f"{p.relative_to(ROOT)}: broken link {target}")
    if errors:raise SystemExit("\n".join(errors))
    print(f"PASS: {len(index)} evidence files unchanged; complete coverage, datasets, provenance and links valid.")


if __name__=="__main__":
    main()
