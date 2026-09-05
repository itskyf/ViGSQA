#!/usr/bin/env python3
"""Vietnamese error taxonomy over sealed per-question evidence.

Classifies every question of one sealed run by failure stage — using the
paper's error-binning thresholds (text F1 ≥ 0.5, error ≤ 0.1) — and flags
measurable Vietnamese-specific phenomena. Sealed artifacts are read-only;
CSV output lands under `results/analysis/`.
"""

import argparse
import csv
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from records_to_answer import exec_rows, load_dataset, rescue_block
from report_split_metrics import load_split
from run_evaluation import gold_values, text_score

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "results" / "evaluation"
CACHE_ROOT = ROOT / "baselines" / "cache_vi" / "pv-26b1ac0d"
OUT_DIR = ROOT / "results" / "analysis"
MODELS = (
    "ornith-ai/Ornith-1.5-9B-NVFP4",
    "AxionML/Qwen3.5-9B-NVFP4",
)
# Paper thresholds (references/main.tex ~L1819): analysis only, never scoring.
TEXT_PASS, ERROR_PASS = 0.5, 0.1


def strip_diacritics(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def primary_metric(row: dict) -> tuple[str, float, bool]:
    """Family-primary metric as (kind, value, attempted)."""
    metrics = row["metrics"]
    if row["family"] in ("entity", "textual_fact"):
        score = metrics["text"]
        return "f1", score["f1"], score["attempted"]
    score = metrics.get("spatial") or metrics.get("angle") or metrics["relative"]
    return "error", score["error"], score["attempted"]


def is_correct(row: dict) -> bool:
    kind, value, _attempted = primary_metric(row)
    return value >= TEXT_PASS if kind == "f1" else value <= ERROR_PASS


def classify(
    row: dict, parse_ok: bool, exec_record: dict | None, rescuable: bool
) -> str:
    if not parse_ok:
        return "parse-failure"
    if is_correct(row):
        return "correct"
    if row["candidates"]:
        return "wrong-attempted"
    if exec_record is None:
        return "refused"  # Direct: no SQL stage; probe showed these are real refusals
    if any(statement.get("error") for statement in exec_record.get("records", [])):
        return "sql-error"
    if not exec_rows(exec_record):
        return "no-rows"
    return "rescuable" if rescuable else "rows-unusable"


def phenomena(row: dict, question: dict, geocodes: dict) -> list[str]:
    """Measurable Vietnamese-specific flags for one question."""
    flags = []
    family = row["family"]
    attempted_text = row["candidates"] and not is_correct(row)
    if family in ("entity", "textual_fact") and attempted_text:
        golds = gold_values(question, family)
        stripped = max(
            (
                text_score(strip_diacritics(pred), strip_diacritics(gold))["f1"]
                for pred in row["candidates"]
                for gold in golds
            ),
            default=0.0,
        )
        if stripped >= TEXT_PASS:
            flags.append("diacritic_loss")
    if family == "location" and row["candidates"]:
        if any(
            geocodes.get(address, {}).get("status", "not_found") != "found"
            for address in row["candidates"]
        ):
            flags.append("geocode_miss")
    if family == "direction" and row["metrics"]["text"]["f1"] >= TEXT_PASS:
        if row["metrics"]["angle"]["error"] > ERROR_PASS:
            flags.append("sector_right_angle_wrong")
    return flags


def parse_ok(record: dict) -> bool:
    if "error" in record or not record.get("content"):
        return False
    return "```" in record["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODELS[0], choices=MODELS)
    parser.add_argument(
        "--baseline", default="text2sql", choices=("direct", "text2sql")
    )
    parser.add_argument("--split", default="all", choices=("dev", "test", "all"))
    parser.add_argument(
        "--examples", type=int, default=2, help="examples printed per stage"
    )
    args = parser.parse_args()

    sealed_dir = EVAL_DIR / args.model / args.baseline
    parse_file = (
        "direct_json_parse.json" if args.baseline == "direct" else "sql_json_parse.json"
    )
    per_question = {
        json.loads(line)["id"]: json.loads(line)
        for line in (sealed_dir / "per_question.jsonl").open(encoding="utf-8")
    }
    parse_records = {
        record["id"]: record
        for record in json.loads((sealed_dir / parse_file).read_text())
    }
    geocodes = {
        record["address"]: record
        for record in json.loads((sealed_dir / "geocodes.json").read_text())
    }
    exec_records = None
    if args.baseline == "text2sql":
        exec_records = {
            record["id"]: record
            for record in json.loads(
                (CACHE_ROOT / args.model / "sql_exec.json").read_text()
            )
        }
    questions = {question["id"]: question for question in load_dataset()}
    splits = load_split()

    rows = []
    for qid, row in sorted(per_question.items()):
        if args.split != "all" and qid not in splits[args.split]:
            continue
        exec_record = exec_records.get(qid) if exec_records is not None else None
        rescuable = False
        if exec_record is not None and not row["candidates"]:
            rescuable = rescue_block(row["family"], exec_rows(exec_record)) is not None
        stage = classify(row, parse_ok(parse_records[qid]), exec_record, rescuable)
        rows.append(
            {
                "id": qid,
                "tid": row["tid"],
                "family": row["family"],
                "stage": stage,
                "flags": ";".join(phenomena(row, questions[qid], geocodes)),
                "question": questions[qid]["question"],
                "prediction": "; ".join(str(c) for c in row["candidates"][:3])[:120],
                "correct": is_correct(row),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"taxonomy_{args.model.split('/')[-1]}_{args.baseline}_{args.split}.csv"
    with (OUT_DIR / name).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    run = f"{args.model.split('/')[-1]}/{args.baseline} [{args.split}]"
    stage_by_family = defaultdict(Counter)
    for row in rows:
        stage_by_family[row["family"]][row["stage"]] += 1
    stages = sorted(
        {stage for counter in stage_by_family.values() for stage in counter}
    )
    print(f"\n### Stage x family — {run}\n")
    print("| family | " + " | ".join(stages) + " |")
    print("|---" * (len(stages) + 1) + "|")
    for family in sorted(stage_by_family):
        cells = [str(stage_by_family[family][stage]) for stage in stages]
        print(f"| {family} | " + " | ".join(cells) + " |")

    flag_counts = Counter(
        flag for row in rows for flag in row["flags"].split(";") if flag
    )
    print(f"\nVietnamese-phenomena flags: {dict(flag_counts) or 'none'}")

    print(f"\n### Representative examples — {run}\n")
    for stage in stages:
        picked = [row for row in rows if row["stage"] == stage][: args.examples]
        for row in picked:
            gold = gold_values(questions[row["id"]], row["family"])
            gold_text = "; ".join(str(g) for g in gold[:2])[:90]
            print(
                f"- **{stage}** `{row['id']}` ({row['tid']}, "
                f"flags: {row['flags'] or '—'}): {row['question'][:100]} "
                f"→ pred: {row['prediction'] or '∅'} | gold: {gold_text}"
            )
    print(f"\nWrote {OUT_DIR / name} ({len(rows)} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
