#!/usr/bin/env python3
"""Create the frozen dev/test split sidecar for the ViGSQA v3 benchmark.

The split is an additive experiment artifact: the 28 question files stay
byte-identical (pinned by `scripts/v3.0.0.sha256`) and only the QID
assignment is recorded, under `docs/`. Stratification is by TID because v3
holds exactly 100 questions per canonical TID.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
QUESTIONS_DIR = ROOT / "generator" / "questions_vi"
SPLIT_PATH = ROOT / "docs" / "dev_test_split_v3.0.0.json"
SPLIT_SALT = "vigsqa-devtest-v1"
DEV_PER_TID = 20
EXPECTED_TIDS = 28
EXPECTED_PER_TID = 100


def dev_test_split() -> dict:
    """Assign the first 20 salted-hash-ranked QIDs of each TID to dev."""
    manifest = json.loads((QUESTIONS_DIR / "MANIFEST.json").read_text())
    by_tid = defaultdict(list)
    for path in sorted(QUESTIONS_DIR.glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            record = json.loads(line)
            by_tid[record["tid"]].append(record["id"])
    if len(by_tid) != EXPECTED_TIDS:
        raise SystemExit(f"expected {EXPECTED_TIDS} TIDs, found {len(by_tid)}")
    dev = {}
    for tid, qids in sorted(by_tid.items()):
        if len(qids) != EXPECTED_PER_TID or len(set(qids)) != len(qids):
            raise SystemExit(
                f"{tid}: expected {EXPECTED_PER_TID} unique QIDs, found {len(qids)}"
            )
        ranked = sorted(
            qids,
            key=lambda qid: hashlib.sha256(f"{SPLIT_SALT}::{qid}".encode()).hexdigest(),
        )
        dev[tid] = ranked[:DEV_PER_TID]
    return {
        "version": "v1",
        "benchmark": manifest["version"],
        "dataset_sha256": manifest["dataset_sha256"],
        "method": (
            f"per TID, QIDs ranked by ascending sha256('{SPLIT_SALT}::<qid>'); "
            f"the first {DEV_PER_TID} are dev, the rest are test"
        ),
        "counts": {
            "dev": EXPECTED_TIDS * DEV_PER_TID,
            "test": EXPECTED_TIDS * (EXPECTED_PER_TID - DEV_PER_TID),
        },
        "dev_qids_per_tid": dev,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="assert the committed artifact matches a fresh derivation",
    )
    args = parser.parse_args()
    text = json.dumps(dev_test_split(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if SPLIT_PATH.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{SPLIT_PATH} differs from a fresh derivation")
        print(f"OK: {SPLIT_PATH.name} matches a fresh derivation")
        return 0
    SPLIT_PATH.write_text(text, encoding="utf-8")
    print(f"Wrote {SPLIT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
