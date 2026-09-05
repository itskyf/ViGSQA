#!/usr/bin/env python3
"""Deterministic records→answer rescue (Text2SQL, Ornith).

Pre-registered rule, frozen before any test aggregate is computed: when the
sealed run produced no answer candidates for a question (worst-case floor —
F1 0 / error 1.0) but SQL execution returned usable typed rows, emit the
typed value from those rows as the answer through the same fenced-JSON shape
the parser produces. All typing and filtering then happens inside the sealed
`candidates()`/`finite_number()` paths imported verbatim from
`run_evaluation.py`; no LLM is called and no sealed file is modified.

Because the rescue only fires where the sealed score already sits at the
floor, per-question scores can only improve or tie (asserted after each
evaluation). Output artifacts live under `results/rescue/` only.
"""

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from report_split_metrics import aggregate, load_split
from run_evaluation import TID_FAMILIES, candidates, evaluate, load_geocodes

from baselines import pipeline

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
MODEL = "ornith-ai/Ornith-1.5-9B-NVFP4"
BASELINE = "text2sql"
SEALED_DIR = ROOT / "results" / "evaluation" / MODEL / BASELINE
CACHE_DIR = ROOT / "baselines" / "cache_vi" / "pv-26b1ac0d" / MODEL
OUT_DIR = ROOT / "results" / "rescue"
NAME_COLS = ("poi_name", "park_name", "lake_name", "road_name")
ADDR_COLS = (
    "addr_housenumber",
    "addr_street",
    "addr_place",
    "addr_suburb",
    "addr_district",
    "addr_city",
    "addr_province",
    "addr_postcode",
)


def load_dataset() -> list[dict]:
    questions = []
    for path in sorted((ROOT / "generator" / "questions_vi").glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            questions.append(json.loads(line))
    return questions


def exec_rows(exec_record: dict) -> list[dict]:
    """Flatten non-error statement outputs into a single row list."""
    rows = []
    for statement in exec_record.get("records", []):
        if statement.get("error"):
            return []
        output = statement.get("output")
        if isinstance(output, list):
            rows.extend(row for row in output if isinstance(row, dict))
    return rows


def canonical_address(row: dict) -> str:
    """Mirror `generator.generator_vi.canonical_address` for exec rows.

    The component order is the published schema (dataset MANIFEST), so this
    is format knowledge, not gold leakage.
    """
    parts = []
    street = " ".join(
        str(row[c]) for c in ("addr_housenumber", "addr_street") if row.get(c)
    )
    specific = street or (str(row["addr_place"]) if row.get("addr_place") else "")
    if specific:
        parts.append(specific)
    for col in ("addr_suburb", "addr_district", "addr_city", "addr_province"):
        if row.get(col) and str(row[col]) not in parts:
            parts.append(str(row[col]))
    if row.get("addr_postcode"):
        parts.append(str(row["addr_postcode"]))
    return ", ".join(parts)


def rescue_block(family: str, rows: list[dict]) -> dict | None:
    """Typed JSON block built from execution rows, or None if unusable.

    Values pass through unchanged; the sealed `candidates()` filter decides
    what is actually scoreable.
    """
    if family == "textual_fact":
        return None  # out-of-schema by verifier design; never rescued
    if family == "entity":
        names = [
            next(
                (str(row[c]) for c in NAME_COLS if row.get(c) and str(row[c]).strip()),
                None,
            )
            for row in rows
        ]
        names = [name for name in names if name]
        return {"name": names} if names else None
    if family == "location":
        addresses = []
        for row in rows:
            address = (
                str(row["address"]).strip()
                if row.get("address")
                else canonical_address(row)
            )
            if address:
                addresses.append(address)
        return {"address": addresses} if addresses else None
    if family == "direction":
        values = [
            row["angle"] for row in rows if isinstance(row.get("angle"), (int, float))
        ]
        return {"azimuth_angle": values[0]} if values else None
    values = [row[family] for row in rows if isinstance(row.get(family), (int, float))]
    return {family: values[0]} if values else None


def load_sealed() -> tuple[dict, dict, dict]:
    """Per-QID sealed evaluation rows, parser records, and execution records."""
    per_question = {
        json.loads(line)["id"]: json.loads(line)
        for line in (SEALED_DIR / "per_question.jsonl").open(encoding="utf-8")
    }
    parse_records = {
        record["id"]: record
        for record in json.loads((SEALED_DIR / "sql_json_parse.json").read_text())
    }
    exec_records = {
        record["id"]: record
        for record in json.loads((CACHE_DIR / "sql_exec.json").read_text())
    }
    return per_question, parse_records, exec_records


def rescues_for(qids: set[str]) -> dict[str, dict]:
    """Rescue JSON block per QID, only where the sealed arm is at the floor."""
    per_question, _, exec_records = load_sealed()
    found = {}
    for qid in sorted(qids):
        sealed = per_question[qid]
        if sealed["candidates"]:
            continue  # fallback-only: never touch questions the model answered
        block = rescue_block(sealed["family"], exec_rows(exec_records[qid]))
        if block is not None:
            found[qid] = block
    return found


def _sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def cmd_gate(args: argparse.Namespace) -> int:
    # Dev counts only: the go/no-go decision and the frozen manifest must not
    # consume test evidence. Test-stage counts appear in summary_test.json
    # after the freeze.
    dev_qids = load_split()["dev"]
    per_question, _, exec_records = load_sealed()
    rescue = rescues_for(dev_qids)
    counts = defaultdict(lambda: defaultdict(int))
    for qid in sorted(dev_qids):
        sealed = per_question[qid]
        if sealed["candidates"]:
            stage = "answered"
        elif rescue.get(qid):
            stage = "rescuable"
        elif any(s.get("error") for s in exec_records[qid].get("records", [])):
            stage = "sql-error"
        elif not exec_rows(exec_records[qid]):
            stage = "no-rows"
        else:
            stage = "rows-unusable"
        counts[sealed["family"]][stage] += 1
    print("| family | answered | rescuable | sql-error | no-rows | rows-unusable |")
    print("|---|---|---|---|---|---|")
    for family, stages in sorted(counts.items()):
        print(
            f"| {family} | {stages['answered']} | {stages['rescuable']} | "
            f"{stages['sql-error']} | {stages['no-rows']} | {stages['rows-unusable']} |"
        )
    dev_rescuable = sum(v["rescuable"] for v in counts.values())
    print(f"\nDev rescuable: {dev_rescuable}/560 questions")
    manifest = {
        "intervention": "records-to-answer-rescue-v1",
        "arm": f"{MODEL}/{BASELINE}",
        "rule": (
            "fallback-only: where sealed candidates are empty and sql_exec rows "
            "carry usable typed values, emit {name|address|azimuth_angle|family-key} "
            "from the rows; typed via sealed candidates()/finite_number"
        ),
        "inputs_sha256": {
            "per_question.jsonl": _sha256(SEALED_DIR / "per_question.jsonl"),
            "sql_exec.json": _sha256(CACHE_DIR / "sql_exec.json"),
            "sql_json_parse.json": _sha256(SEALED_DIR / "sql_json_parse.json"),
            "dev_test_split": _sha256(
                SCRIPT_DIR.parent / "docs" / "dev_test_split_v3.0.0.json"
            ),
        },
        "gate_counts": {
            family: dict(stages) for family, stages in sorted(counts.items())
        },
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "intervention.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Froze intervention manifest: {OUT_DIR / 'intervention.json'}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    splits = load_split()
    qids = splits[args.split]
    questions = [q for q in load_dataset() if q["id"] in qids]
    per_question, parse_records, _ = load_sealed()
    rescue = rescues_for(qids)

    merged = []
    rescued_rows = []
    for question in questions:
        qid = question["id"]
        record = parse_records[qid]
        if qid in rescue:
            block = rescue[qid]
            merged.append(
                {
                    "id": qid,
                    "content": "```json\n"
                    + json.dumps(block, ensure_ascii=False)
                    + "\n```",
                }
            )
            rescued_rows.append(
                {"id": qid, "family": per_question[qid]["family"], "rescued": block}
            )
        else:
            merged.append({"id": qid, "content": record.get("content", "")})
    print(f"[{args.split}] rescued {len(rescued_rows)} of {len(questions)} questions")

    # Warm-start geocoding from the sealed run: identical address strings keep
    # their sealed coordinates; only genuinely new addresses hit Nominatim.
    # One file per split — load_geocodes rewrites the file to exactly the
    # addresses of one run, so a shared file would drop the other split's
    # warm start and force hundreds of re-queries.
    geocode_path = OUT_DIR / f"geocodes_{args.split}.json"
    if not geocode_path.exists():
        shutil.copyfile(SEALED_DIR / "geocodes.json", geocode_path)
    address_order = []
    for question, record in zip(questions, merged, strict=True):
        if per_question[question["id"]]["family"] != "location":
            continue
        parsed = pipeline.extract_json_blocks(record.get("content", ""))
        for address in candidates(question, parsed, TID_FAMILIES[question["tid"]]):
            if address not in address_order:
                address_order.append(address)
    new_addresses = 0
    known = {r["address"] for r in json.loads(geocode_path.read_text())}
    new_addresses = sum(1 for a in address_order if a not in known)
    geocoder = RateLimiter(
        Nominatim(user_agent="ViGSQA-records-rescue", timeout=10).geocode,
        min_delay_seconds=1,
        max_retries=2,
        error_wait_seconds=5,
        swallow_exceptions=False,
    )
    geocodes = load_geocodes(geocode_path, address_order, geocoder)
    print(f"[{args.split}] geocoded {new_addresses} new addresses")

    rows = evaluate(questions, merged, geocodes)
    for row in rows:
        row.update(model=MODEL, baseline=f"{BASELINE}+rescue")

    # Regression floor: the rescue must never lower a sealed score.
    regressions = []
    for row in rows:
        sealed = per_question[row["id"]]
        for metric, value in row["metrics"].items():
            before = sealed["metrics"][metric]
            if metric == "text":
                ok = value["f1"] >= before["f1"] - 1e-12
            else:
                ok = value["error"] <= before["error"] + 1e-12
            if not ok:
                regressions.append((row["id"], metric, before, value))
    if regressions:
        for qid, metric, before, after in regressions[:10]:
            print(f"REGRESSION {qid} {metric}: {before} -> {after}")
        raise SystemExit(
            f"{len(regressions)} per-question regressions — rescue invariant violated"
        )

    arm = aggregate(rows)
    baseline = aggregate(
        [sealed for qid, sealed in per_question.items() if qid in qids]
    )
    print(f"\n### {args.split}: Ornith Text2SQL baseline → +rescue\n")
    print("| family | metric | baseline | rescue | delta |")
    print("|---|---|---|---|---|")
    for family in sorted(arm):
        for column in arm[family]:
            if column == "n" or column.endswith("_attempted"):
                continue
            before, after = baseline[family][column], arm[family][column]
            delta = after - before
            better = delta > 0 if column == "text_f1" else delta < 0
            mark = "↑" if better else ("≈" if delta == 0 else "↓")
            cells = [
                family,
                column,
                f"{before:.3f}",
                f"{after:.3f}",
                f"{delta:+.3f} {mark}",
            ]
            print("| " + " | ".join(cells) + " |")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"per_question_{args.split}.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    (OUT_DIR / f"rescued_{args.split}.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rescued_rows
        ),
        encoding="utf-8",
    )
    summary = {
        "split": args.split,
        "questions": len(rows),
        "rescued": len(rescued_rows),
        "regressions": 0,
        "baseline": baseline,
        "rescue": arm,
    }
    (OUT_DIR / f"summary_{args.split}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote per_question/rescued/summary for {args.split} to {OUT_DIR}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "gate",
        help="count dev/test recoverability and freeze the intervention manifest",
    )
    eval_parser = sub.add_parser("eval", help="evaluate the rescue arm on a split")
    eval_parser.add_argument("--split", required=True, choices=("dev", "test"))
    args = parser.parse_args()
    return cmd_gate(args) if args.command == "gate" else cmd_eval(args)


if __name__ == "__main__":
    raise SystemExit(main())
