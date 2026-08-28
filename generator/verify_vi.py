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
    f) Anchor exclusion: SQL must exclude the anchor POI id, and no answer may
       carry the excluded id or the anchor entity's geometry
    g) Determinism: no LIMIT unless the statement also has ORDER BY
    h) Record identity: stable `{type}-NNN` id present; type matches filename
    i) Surfaces: question equals question_surfaces.full; no duplicate questions

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
import random
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# Record count every question file is expected to hold.
EXPECTED_RECORD_COUNT = 100

# ── Layer 2 checks ───────────────────────────────────────────────────────────


def check_nfc(text: str) -> bool:
    return unicodedata.normalize("NFC", text) == text


def check_no_placeholders(text: str) -> bool:
    return not re.search(r"\[[\d\w]+\]", text)


def check_length(text: str, min_chars: int = 10, max_chars: int = 300) -> bool:
    return min_chars <= len(text) <= max_chars


def check_diacritic_surfaces(full: str, stripped: str) -> bool:
    # stripped must differ from full IF full contains Vietnamese diacritics
    vn_chars = re.compile(
        r"[àáảãạăắặẳẵằâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđÀÁẢÃẠĂẮẶẲẴẰÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]"
    )
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


# Matches the anchor-exclusion predicate the generators emit, e.g. `id <> 123`
# or `p.osm_id <> 123`.
ANCHOR_EXCLUSION_RE = re.compile(r"\b(?:p\.)?(?:osm_id|id)\s*<>\s*(\d+)")


def excluded_anchor_ids(sql: str) -> set[str]:
    """Anchor POI ids the SQL excludes (empty set when no exclusion exists)."""
    return {m.group(1) for m in ANCHOR_EXCLUSION_RE.finditer(sql)}


def check_limit_ordered(sql: str) -> bool:
    """A LIMIT must be backed by ORDER BY, otherwise the stored subset is
    planner-dependent."""
    s = sql.upper()
    return "LIMIT" not in s or "ORDER BY" in s


@dataclass
class CheckResult:
    question_id: int
    question: str
    template_type: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_layer2(entry: dict, idx: int, expected_type: str | None = None) -> CheckResult:
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

    # anchor exclusion: the anchor POI must not be able to answer its own question
    excluded = excluded_anchor_ids(sql)
    if not excluded:
        failures.append(
            "SQL_NO_ANCHOR_EXCLUSION: anchor POI can appear in its own answers"
        )
    for ans in answers:
        if str(ans.get("id", "")) in excluded:
            failures.append(
                f"SELF_ANCHOR: answer id {ans.get('id')} equals the excluded anchor id"
            )
    anchor_wkts = {
        v.get("geo_wkt")
        for v in entities.values()
        if isinstance(v, dict) and v.get("geo_wkt")
    }
    for ans in answers:
        if ans.get("geo_wkt") in anchor_wkts:
            failures.append(
                "SELF_ANCHOR_WKT: answer geometry equals the anchor entity geometry"
            )

    # determinism: a bare LIMIT stores an arbitrary subset of the true answers
    if not check_limit_ordered(sql):
        failures.append("LIMIT_WITHOUT_ORDER_BY: answer subset is nondeterministic")

    # stable record identity and type/filename agreement
    qid = entry.get("id")
    if not isinstance(qid, str) or not re.fullmatch(
        rf"{re.escape(qtype)}-\d{{3}}", qid
    ):
        failures.append(f"BAD_QUESTION_ID: expected '{qtype}-NNN', got {qid!r}")
    if expected_type is not None and qtype != expected_type:
        failures.append(
            f"TYPE_MISMATCH: record type {qtype!r} != filename type {expected_type!r}"
        )

    # the two surfaces must agree with the canonical question
    if full != q:
        failures.append("SURFACE_MISMATCH: question != question_surfaces.full")

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
    for group in by_type.values():
        k = max(1, int(len(group) * rate))
        sample.extend(random.sample(group, min(k, len(group))))
    return sample


def print_spot_check_tsv(sample: list[dict]):
    print("id\ttype\tquestion\texpected_answer\tannotation")
    for i, e in enumerate(sample):
        q = e.get("question", "")
        qtype = e.get("type", "")
        ans = e.get("answers", [{}])
        ans_name = (
            ans[0].get("poi_name") or ans[0].get("road_name") or str(ans[0])[:60]
            if ans
            else ""
        )
        print(f"{e.get('id', i)}\t{qtype}\t{q}\t{ans_name}\t")


# ── Main ──────────────────────────────────────────────────────────────────────


def load_jsonl(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                entries.append(json.loads(stripped))
    return entries


def verify_file(path: Path, spot_rate: float = 0.0) -> tuple[int, int]:
    entries = load_jsonl(path)
    passed = 0
    failed = 0
    fail_log = []
    seen_questions: set[str] = set()

    for i, entry in enumerate(entries):
        result = run_layer2(entry, i, expected_type=path.stem)
        if entry.get("question") in seen_questions:
            result.failures.append(
                "DUPLICATE: identical question text earlier in this file"
            )
            result.passed = False
        else:
            seen_questions.add(entry.get("question", ""))
        if result.passed:
            passed += 1
        else:
            failed += 1
            fail_log.append(result)
        if result.warnings:
            for w in result.warnings:
                print(f"  WARN [{i}] {w}", file=sys.stderr)

    if len(entries) != EXPECTED_RECORD_COUNT:
        print(
            f"  WARN: {path.name}: expected 100 records, found {len(entries)}",
            file=sys.stderr,
        )

    print(f"\n{path.name}: {passed} passed / {failed} failed / {len(entries)} total")

    if fail_log:
        print("\nFAILURES:")
        for r in fail_log[:20]:
            print(f"  [{r.question_id}] {r.template_type}: {'; '.join(r.failures)}")
            print(f"    Q: {r.question[:100]}")

    if spot_rate > 0:
        sample = spot_check_sample(entries, spot_rate)
        print(f"\n── Spot-check sample ({spot_rate * 100:.0f}%, n={len(sample)}) ──")
        print_spot_check_tsv(sample)

    return passed, failed


def main():
    parser = argparse.ArgumentParser(description="Verify Vietnamese GeoQA data")
    parser.add_argument(
        "--input", required=True, help="JSONL file or directory of JSONL files"
    )
    parser.add_argument(
        "--all", action="store_true", help="Process all .jsonl files in directory"
    )
    parser.add_argument(
        "--spot-check",
        type=float,
        default=0.0,
        help="Fraction for human spot-check TSV output (e.g. 0.05)",
    )
    parser.add_argument(
        "--seed", type=int, help="Seed for reproducible spot-check sampling"
    )
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

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
