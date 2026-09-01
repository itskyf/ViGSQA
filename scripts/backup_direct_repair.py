"""Back up structurally invalid Direct artifacts before the bounded repair."""

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from baselines.pipeline import extract_json_blocks
from scripts.run_check import namespaced_cache_dir

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    cache_dir = namespaced_cache_dir() / args.model
    paths = [cache_dir / "direct_answer.json", cache_dir / "direct_json_parse.json"]
    records = [json.loads(path.read_text()) for path in paths]
    invalid = {
        "direct_answer": sum(
            not r.get("error") and not r.get("content", "").strip() for r in records[0]
        ),
        "direct_json_parse": sum(
            not r.get("error") and not extract_json_blocks(r.get("content", ""))
            for r in records[1]
        ),
    }
    if not any(invalid.values()):
        print("[INFO] Ornith Direct needs no structural repair backup.")
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "logs" / "official" / f"pre_direct_integrity_{stamp}"
    out.mkdir(parents=True)
    evidence = paths[:]
    manifests = sorted(
        (ROOT / "logs" / "official").glob("*Ornith*direct*.manifest.json")
    )
    if manifests:
        evidence.append(manifests[-1])
    checksums = []
    for path in evidence:
        target = out / path.name
        shutil.copy2(path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {target.name}")
    (out / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
    (out / "invalid_counts.json").write_text(json.dumps(invalid, indent=2) + "\n")
    print(f"[INFO] Backed up invalid Ornith Direct artifacts to {out}")


if __name__ == "__main__":
    main()
