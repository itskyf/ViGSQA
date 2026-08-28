"""G6 completion asserts + minimal run manifest for one v2.0.0 baseline run.

Run by scripts/run_official_v2.sh right after each baseline finishes. Asserts
the raw caches are complete against the frozen questions, then writes a
minimal manifest (git commit, dataset/OSM provenance, model, prompt hash,
baseline, timestamps, completed/failed counts).

Usage:
    python scripts/run_check_v2.py --model llamacpp:org/repo:QUANT \
        --baseline text2sql --log logs/v2.0.0/<run_prefix>
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = ROOT / "generator" / "questions_vi"
CACHE_ROOT = ROOT / "baselines" / "cache_vi"
EXPECTED_QUESTIONS = 2800
EXPECTED_TIDS = 28
EXPECTED_PER_TID = 100
STEPS = {
    "direct": ["direct_answer", "direct_json_parse"],
    "text2sql": ["sql_generate", "sql_exec", "sql_answer", "sql_json_parse"],
}


def load_questions() -> list[dict]:
    questions = []
    for path in sorted(QUESTIONS_DIR.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            questions.extend(json.loads(line) for line in f if line.strip())
    return questions


def namespaced_cache_dir() -> Path:
    """The single ds-*/pv-* namespace baselines_vi.py created for this freeze."""
    matches = sorted(CACHE_ROOT.glob("ds-*/pv-*"))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one cache namespace under {CACHE_ROOT}, "
            f"found {[m.name for m in matches]}"
        )
    return matches[0]


def osm_snapshot() -> dict:
    """Pinned PBF URL + sha256 as hardcoded in scripts/download_osm.sh."""
    src = (ROOT / "scripts" / "download_osm.sh").read_text()
    url = re.search(r'OSM_URL="([^"]+)"', src)
    checksum = re.search(r'OSM_SHA256="([0-9a-fA-F]{64})"', src)
    if not url or not checksum:
        raise SystemExit("could not parse the pinned OSM snapshot from download_osm.sh")
    return {"url": url.group(1), "sha256": checksum.group(1).upper()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--baseline", required=True, choices=sorted(STEPS))
    parser.add_argument(
        "--log", required=True, help="run log path prefix (…/<run>.out)"
    )
    args = parser.parse_args()

    log_prefix = args.log.removesuffix(".out")

    questions = load_questions()

    # ── Question-side asserts ────────────────────────────────────────────────
    ids = [q["id"] for q in questions]
    assert len(ids) == EXPECTED_QUESTIONS, (
        f"expected {EXPECTED_QUESTIONS} questions, found {len(ids)}"
    )
    assert len(set(ids)) == EXPECTED_QUESTIONS, "duplicate question ids"
    per_tid: dict[str, int] = {}
    for q in questions:
        per_tid[q["tid"]] = per_tid.get(q["tid"], 0) + 1
    assert len(per_tid) == EXPECTED_TIDS, (
        f"expected {EXPECTED_TIDS} tids, found {len(per_tid)}"
    )
    assert all(n == EXPECTED_PER_TID for n in per_tid.values()), (
        f"not 100 per tid: {per_tid}"
    )
    question_ids = set(ids)

    # ── Cache-side asserts ───────────────────────────────────────────────────
    cache_dir = namespaced_cache_dir()
    step_stats = {}
    for step in STEPS[args.baseline]:
        records = json.loads((cache_dir / args.model / f"{step}.json").read_text())
        record_ids = {r["id"] for r in records}
        assert record_ids == question_ids, (
            f"{step}: {len(question_ids - record_ids)} question ids missing from cache"
        )
        failed = [r for r in records if r.get("error")]
        if step == "sql_generate":
            empty_sql = [
                r["id"]
                for r in records
                if not r.get("error") and "```sql" not in r.get("content", "")
            ]
            assert not empty_sql, f"{step}: non-failed records without sql blocks"
        if step == "sql_exec":
            missing = [r["id"] for r in records if "records" not in r]
            assert not missing, f"{step}: records without raw execution results"
        step_stats[step] = {"records": len(records), "failed": len(failed)}
        print(f"  {step}: {len(records)} records, {len(failed)} explicit failures")

    # ── Minimal manifest ─────────────────────────────────────────────────────
    manifest = {
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "dataset_manifest": json.loads((QUESTIONS_DIR / "MANIFEST.json").read_text()),
        "osm_snapshot": osm_snapshot(),
        "model": args.model,
        "baseline": args.baseline,
        "prompt_version": cache_dir.name.removeprefix("pv-"),
        "started": Path(f"{log_prefix}.start_ts").read_text().strip(),
        "finished": subprocess.run(
            ["date", "--iso-8601=seconds"], capture_output=True, text=True, check=False
        ).stdout.strip(),
        "steps": step_stats,
    }
    out_path = Path(f"{log_prefix}.manifest.json")
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"  manifest: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
