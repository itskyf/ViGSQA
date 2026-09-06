#!/usr/bin/env python3
"""Derive dev/test baseline tables from the sealed T03 per-question results.

Read-only over sealed artifacts: `per_question.jsonl` rows are consumed
exactly as sealed and grouped by the frozen split
(`docs/dev_test_split_v3.0.0.json`). Means include unattempted questions,
which carry their worst-case values (F1 0 / error 1.0) — the paper's §5.1
semantics. No scoring code is re-run and no sealed file is modified; the
full CSVs land under `results/analysis/` (regenerable, not committed).
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "results" / "evaluation"
SPLIT_PATH = ROOT / "docs" / "dev_test_split_v3.0.0.json"
OUT_DIR = ROOT / "results" / "analysis"

MODELS = (
    "ornith-ai/Ornith-1.5-9B-NVFP4",
    "AxionML/Qwen3.5-9B-NVFP4",
)
BASELINES = ("direct", "text2sql")
# family -> metric columns: (column name, metrics-dict key, field, kind)
FAMILY_METRICS = {
    "entity": [("text_f1", "text", "f1", "max")],
    "textual_fact": [("text_f1", "text", "f1", "max")],
    "location": [
        ("text_f1", "text", "f1", "max"),
        ("distance_error", "spatial", "error", "min"),
    ],
    "direction": [
        ("text_f1", "text", "f1", "max"),
        ("angle_error", "angle", "error", "min"),
    ],
    "count": [("relative_error", "relative", "error", "min")],
    "distance": [("relative_error", "relative", "error", "min")],
    "area": [("relative_error", "relative", "error", "min")],
    "length": [("relative_error", "relative", "error", "min")],
}


def load_split() -> dict[str, set[str]]:
    """Return QID sets per split from the frozen sidecar."""
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    qids = {
        name: {
            qid
            for tid in sorted(split["dev_qids_per_tid"])
            for qid in split["dev_qids_per_tid"][tid]
        }
        for name in ("dev",)
    }
    qids["test"] = set()
    for path in sorted((ROOT / "generator" / "questions_vi").glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            record = json.loads(line)
            if record["id"] not in qids["dev"]:
                qids["test"].add(record["id"])
    return qids


def run_rows(model: str, baseline: str) -> list[dict]:
    path = EVAL_DIR / model / baseline / "per_question.jsonl"
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def aggregate(rows: list[dict]) -> dict:
    """Group sealed rows by family and average each applicable metric."""
    by_family = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)
    out = {}
    for family, family_rows in sorted(by_family.items()):
        entry = {"n": len(family_rows)}
        for column, key, field, _kind in FAMILY_METRICS[family]:
            values = [row["metrics"][key][field] for row in family_rows]
            entry[column] = sum(values) / len(values)
            attempted = [row["metrics"][key]["attempted"] for row in family_rows]
            entry[f"{column}_attempted"] = sum(attempted) / len(attempted)
        out[family] = entry
    return out


def _short(model: str, baseline: str) -> str:
    return (
        f"{'Ornith' if model.startswith('ornith') else 'Qwen'}-{baseline.capitalize()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    splits = load_split()
    if splits["dev"] | splits["test"] != {
        r["id"] for r in run_rows(MODELS[0], "direct")
    }:
        raise SystemExit("split QIDs do not partition the benchmark")

    csv_rows = []
    per_tid_rows = []
    for model in MODELS:
        for baseline in BASELINES:
            rows = run_rows(model, baseline)
            for split_name in ("dev", "test"):
                subset = [row for row in rows if row["id"] in splits[split_name]]
                if len(subset) != (560 if split_name == "dev" else 2240):
                    raise SystemExit(
                        f"{model}/{baseline}/{split_name}: "
                        f"expected 560/2240 rows, got {len(subset)}"
                    )
                for family, entry in aggregate(subset).items():
                    csv_rows.append(
                        {
                            "model": model,
                            "baseline": baseline,
                            "run": _short(model, baseline),
                            "split": split_name,
                            "family": family,
                            **entry,
                        }
                    )
                by_tid = defaultdict(list)
                for row in subset:
                    by_tid[row["tid"]].append(row)
                for tid, tid_rows in sorted(by_tid.items()):
                    for family, entry in aggregate(tid_rows).items():
                        per_tid_rows.append(
                            {
                                "model": model,
                                "baseline": baseline,
                                "run": _short(model, baseline),
                                "split": split_name,
                                "tid": tid,
                                "family": family,
                                **entry,
                            }
                        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = sorted(
        {key for row in csv_rows for key in row},
        key=lambda k: (k not in ("run", "split", "family"), k),
    )
    with (OUT_DIR / "baseline_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)
    tid_fields = ["run", "split", "tid", "family"] + [
        k for k in fields if k not in ("run", "split", "family")
    ]
    with (OUT_DIR / "baseline_per_tid.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=tid_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(per_tid_rows)
    print(
        f"Wrote {OUT_DIR / 'baseline_metrics.csv'} and "
        f"baseline_per_tid.csv ({len(csv_rows)} family rows)"
    )

    families = sorted({row["family"] for row in csv_rows})
    columns = sorted({row["run"] for row in csv_rows})
    for column_name in ("text_f1", "distance_error", "angle_error", "relative_error"):
        if not any(column_name in row for row in csv_rows):
            continue
        for split_name in ("dev", "test"):
            print(f"\n### {column_name} — {split_name}\n")
            print("| family | " + " | ".join(columns) + " |")
            print("|---" * (len(columns) + 1) + "|")
            for family in families:
                cells = []
                for column in columns:
                    match = next(
                        (
                            r
                            for r in csv_rows
                            if r["split"] == split_name
                            and r["family"] == family
                            and r["run"] == column
                            and column_name in r
                        ),
                        None,
                    )
                    cells.append(f"{match[column_name]:.3f}" if match else "—")
                if any(cell != "—" for cell in cells):
                    print(f"| {family} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
