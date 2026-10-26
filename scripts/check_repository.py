"""Check archived evidence bytes, canonical inputs and relative Markdown links."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    errors = []
    index = json.loads((ROOT / "docs/evidence-sha256.json").read_text(encoding="utf-8"))
    for relative, expected in index.items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f"Evidence changed/missing: {relative}")
    for name, run in (("shared", "shared_off_run1"), ("independent", "independent_cold_off_run1")):
        if (ROOT / f"data/{name}.jsonl").read_bytes() != (ROOT / f"results/prefix-cache/{run}/dataset.jsonl").read_bytes():
            errors.append(f"Canonical dataset differs: {name}")
    for p in ROOT.rglob("*.md"):
        if ".git" in p.parts:
            continue
        text = re.sub(r"```.*?```", "", p.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"!?(?:\[[^\]]*\])\(([^)]+)\)", text):
            target = target.strip("<>").split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (p.parent / target).exists():
                errors.append(f"{p.relative_to(ROOT)}: broken link {target}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {len(index)} evidence files unchanged; datasets and Markdown links valid.")

if __name__ == "__main__":
    main()
