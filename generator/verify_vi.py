"""
Vietnamese GeoQA verification pipeline — 3 layers:

  Layer 1 — SQL execution (automatic, inherited from GS-QA):
    SQL executes on PostGIS → non-empty answer → spatial correctness guaranteed
    by construction. No human needed.

  Layer 2 — Automated text checks (Vietnamese-specific):
    a) Unicode NFC normalization
    b) Placeholder substitution completeness ([1],[2],[3] not left in output)
    c) Minimum/maximum question length heuristic
    d) Diacritic surface consistency (full vs stripped differ where expected)
    e) OSM name sanity (entity names contain at least one Vietnamese-range char
       OR standard ASCII — not garbled encoding)

  Layer 3 — Human spot-check sample:
    Stratified 5% sample per template type, printed as TSV for annotators.
    Annotators mark: correct / incorrect / unclear

Usage:
    python verify_vi.py --input questions_vi/knn+name.jsonl
    python verify_vi.py --input questions_vi/ --all
    python verify_vi.py --input questions_vi/ --spot-check 0.05
"""
import argparse
import json
import unicodedata
import re
import sys
import random
from pathlib import Path
from dataclasses import dataclass, field


# ── Layer 2 checks ───────────────────────────────────────────────────────────

def check_nfc(text: str) -> bool:
    return unicodedata.normalize("NFC", text) == text

def check_no_placeholders(text: str) -> bool:
    return not re.search(r"\[[\d\w]+\]", text)

def check_length(text: str, min_chars: int = 10, max_chars: int = 300) -> bool:
    return min_chars <= len(text) <= max_chars

def check_diacritic_surfaces(full: str, stripped: str) -> bool:
    # stripped must differ from full IF full contains Vietnamese diacritics
    vn_chars = re.compile(r"[àáảãạăắặẳẵằâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđÀÁẢÃẠĂẮẶẲẴẰÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]")
    has_diacritics = bool(vn_chars.search(full))
    if has_diacritics:
        return full != stripped
    return True  # no diacritics → trivially ok

def check_osm_name(name: str) -> bool:
    if not name:
        return False
    # allow: ASCII printable, Vietnamese Unicode range, digits, spaces, punctuation
    # reject: raw bytes, \x escapes, replacement chars
    if "�" in name:
        return False
    if "\\x" in name:
        return False
    return len(name.strip()) > 0

@dataclass
class CheckResult:
    question_id: int
    question: str
    template_type: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_layer2(entry: dict, idx: int) -> CheckResult:
    q = entry.get("question", "")
    qtype = entry.get("type", "unknown")
    surfaces = entry.get("question_surfaces", {})
    full = surfaces.get("full", q)
    stripped = surfaces.get("stripped", q)
    answers = entry.get("answers", [])

    failures = []
    warnings = []

    if not check_nfc(q):
        failures.append("NOT_NFC: question not in Unicode NFC form")

    if not check_no_placeholders(q):
        failures.append(f"PLACEHOLDER_LEAK: unreplaced placeholder in: {q!r}")

    if not check_length(q):
        warnings.append(f"LENGTH: question length {len(q)} outside [10,300]")

    if not check_diacritic_surfaces(full, stripped):
        warnings.append("SURFACE: full and stripped identical but full has diacritics")

    # check OSM entity names in answers
    for ans in answers:
        name = ans.get("poi_name") or ans.get("road_name") or ans.get("park_name") or ""
        if name and not check_osm_name(name):
            failures.append(f"OSM_NAME_GARBLED: {name!r}")

    # check question entities have expected fields
    entities = entry.get("question_entities", {})
    for k, v in entities.items():
        if "poi_name" in v and not check_osm_name(v["poi_name"]):
            failures.append(f"ENTITY_NAME_GARBLED: {k} → {v['poi_name']!r}")

    # SQL sanity: must contain SELECT and FROM
    sql = entry.get("sql", "")
    if "SELECT" not in sql.upper() or "FROM" not in sql.upper():
        failures.append("SQL_MALFORMED: missing SELECT or FROM")

    # empty answers
    if not answers:
        warnings.append("EMPTY_ANSWERS: no answer rows")

    passed = len(failures) == 0
    return CheckResult(idx, q, qtype, passed, failures, warnings)


# ── Layer 3 spot-check sampler ───────────────────────────────────────────────

def spot_check_sample(entries: list[dict], rate: float = 0.05) -> list[dict]:
    """Stratified sample by template type."""
    by_type: dict[str, list] = {}
    for e in entries:
        by_type.setdefault(e.get("type", "unknown"), []).append(e)
    sample = []
    for qtype, group in by_type.items():
        k = max(1, int(len(group) * rate))
        sample.extend(random.sample(group, min(k, len(group))))
    return sample


def print_spot_check_tsv(sample: list[dict]):
    print("id\ttype\tquestion\texpected_answer\tannotation")
    for i, e in enumerate(sample):
        q = e.get("question", "")
        qtype = e.get("type", "")
        ans = e.get("answers", [{}])
        ans_name = ans[0].get("poi_name") or ans[0].get("road_name") or str(ans[0])[:60] if ans else ""
        print(f"{i}\t{qtype}\t{q}\t{ans_name}\t")


# ── Main ──────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def verify_file(path: Path, spot_rate: float = 0.0) -> tuple[int, int]:
    entries = load_jsonl(path)
    passed = 0
    failed = 0
    fail_log = []

    for i, entry in enumerate(entries):
        result = run_layer2(entry, i)
        if result.passed:
            passed += 1
        else:
            failed += 1
            fail_log.append(result)
        if result.warnings:
            for w in result.warnings:
                print(f"  WARN [{i}] {w}", file=sys.stderr)

    print(f"\n{path.name}: {passed} passed / {failed} failed / {len(entries)} total")

    if fail_log:
        print("\nFAILURES:")
        for r in fail_log[:20]:
            print(f"  [{r.question_id}] {r.template_type}: {'; '.join(r.failures)}")
            print(f"    Q: {r.question[:100]}")

    if spot_rate > 0:
        sample = spot_check_sample(entries, spot_rate)
        print(f"\n── Spot-check sample ({spot_rate*100:.0f}%, n={len(sample)}) ──")
        print_spot_check_tsv(sample)

    return passed, failed


def main():
    parser = argparse.ArgumentParser(description="Verify Vietnamese GeoQA data")
    parser.add_argument("--input", required=True, help="JSONL file or directory of JSONL files")
    parser.add_argument("--all", action="store_true", help="Process all .jsonl files in directory")
    parser.add_argument("--spot-check", type=float, default=0.0,
                        help="Fraction for human spot-check TSV output (e.g. 0.05)")
    args = parser.parse_args()

    p = Path(args.input)
    total_pass, total_fail = 0, 0

    if p.is_dir():
        files = sorted(p.glob("*.jsonl"))
        if not files:
            print(f"No .jsonl files found in {p}")
            sys.exit(1)
        for f in files:
            pp, ff = verify_file(f, args.spot_check)
            total_pass += pp
            total_fail += ff
    else:
        total_pass, total_fail = verify_file(p, args.spot_check)

    total = total_pass + total_fail
    pct = 100 * total_pass / total if total else 0
    print(f"\n══ TOTAL: {total_pass}/{total} passed ({pct:.1f}%) ══")
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
