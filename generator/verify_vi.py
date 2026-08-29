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
    f) Anchor exclusion, per family: POI-anchored SQL must exclude the anchor
       id (`id <> N`) and no answer may carry it or the anchor geometry;
       region-anchored SQL must reference the region by id subquery and no
       answer may carry that region id
    g) Determinism: no LIMIT unless the statement also has ORDER BY
    h) Record identity: stable `{type}-NNN` id and `Tnn` tid present; type
       matches filename; answer_type matches the type string's output suffix
    i) Surfaces: question equals question_surfaces.full; no duplicate questions
       (per file and globally across the dataset)
    j) Spatial-op agreement: direction/towards SQL contains ST_Azimuth;
       intersects SQL contains ST_Intersects
    k) Answer payload sanity: `angle` in [0,360), `area`/`length` > 0,
       `count` >= 1, `distance` key present; T7 answers carry the frozen
       multi_source_* fields

  Layer 3 — Human spot-check sample:
    Stratified 5% sample per tid, printed as TSV for annotators.
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

# Azimuth answers span a full turn, [0, 360) degrees.
FULL_TURN_DEG = 360

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

# Matches the region-anchor reference the intersects family emits (regions are
# never inlined as WKT multipolygons).
REGION_SUBQUERY_RE = re.compile(
    r"\(\s*SELECT geometry FROM regions WHERE id = (\d+)\s*\)"
)


# Expected answer_type derived from the type string alone: the segment after
# the final '+' (multi-source types answer with a name).
def expected_answer_type(qtype: str) -> str:
    if "multi_source" in qtype:
        return "name"
    return qtype.rsplit("+", maxsplit=1)[-1]


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

    # anchor exclusion, branched by family: the anchor must never answer its
    # own question. Intersects types anchor on a region id subquery instead
    # of an excluded POI id.
    if qtype.startswith("intersects"):
        if "ST_INTERSECTS" not in sql.upper():
            failures.append(
                "SQL_NO_ST_INTERSECTS: intersects type without ST_Intersects"
            )
        if (
            qtype.endswith(("_total+area", "_total+length"))
            and "SUM" not in sql.upper()
        ):
            failures.append(
                "SQL_NO_SUM: total question answered without SUM aggregation"
            )
        region_ids = {m.group(1) for m in REGION_SUBQUERY_RE.finditer(sql)}
        if not region_ids:
            failures.append("SQL_NO_REGION_SUBQUERY: region not referenced by id")
        for ans in answers:
            if str(ans.get("id", "")) in region_ids:
                failures.append(
                    "SELF_ANCHOR: answer id equals the anchor region id: "
                    f"{ans.get('id')}"
                )
    else:
        excluded = excluded_anchor_ids(sql)
        if not excluded:
            failures.append(
                "SQL_NO_ANCHOR_EXCLUSION: anchor POI can appear in its own answers"
            )
        for ans in answers:
            if str(ans.get("id", "")) in excluded:
                failures.append(
                    "SELF_ANCHOR: answer id equals the excluded anchor id: "
                    f"{ans.get('id')}"
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

    # spatial-operator agreement with the type string
    if ":direction" in qtype or ":towards" in qtype:
        if "ST_AZIMUTH" not in sql.upper():
            failures.append("SQL_NO_ST_AZIMUTH: direction/towards semantics missing")
    if ":towards" in qtype and "BETWEEN" in sql.upper():
        # The naive BETWEEN corridor silently drops candidates when the
        # reference azimuth crosses north; the generator emits a modulo
        # corridor instead. (A string check can only catch known-bad
        # patterns; wrap-safety itself is validated by the spot check.)
        failures.append(
            "SQL_NAIVE_TOWARDS: corridor uses BETWEEN instead of a "
            "wrap-safe modulo predicate"
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

    # tid and answer_type agreement with the type string
    tid = entry.get("tid")
    if not isinstance(tid, str) or not re.fullmatch(r"T\d{2}", tid):
        failures.append(f"BAD_TID: expected 'Tnn', got {tid!r}")
    if entry.get("answer_type") != expected_answer_type(qtype):
        failures.append(
            f"BAD_ANSWER_TYPE: {entry.get('answer_type')!r} != "
            f"{expected_answer_type(qtype)!r} for {qtype!r}"
        )

    # answer payload sanity per answer_type (generator contract)
    for ans in answers:
        try:
            if entry.get("answer_type") == "angle" and not (
                0 <= float(ans["angle"]) < FULL_TURN_DEG
            ):
                failures.append(
                    f"ANGLE_RANGE: angle {ans.get('angle')} outside [0,360)"
                )
            if entry.get("answer_type") in ("area", "length") and not (
                float(ans[entry["answer_type"]]) > 0
            ):
                failures.append(
                    f"{entry['answer_type'].upper()}_NONPOSITIVE: "
                    f"{ans.get(entry['answer_type'])}"
                )
            if entry.get("answer_type") == "distance" and (
                "distance" not in ans or float(ans["distance"]) < 0
            ):
                failures.append(f"BAD_DISTANCE: {ans.get('distance')!r}")
            if entry.get("answer_type") == "count" and not int(ans["count"]) >= 1:
                failures.append(f"NONPOSITIVE_COUNT: {ans.get('count')!r}")
        except (KeyError, TypeError, ValueError):
            failures.append(
                "PAYLOAD_MALFORMED: answer missing its "
                f"{entry.get('answer_type')} value"
            )

    # T7 freezes the external Wikipedia value into the answer row
    if qtype == "knn+name+multi_source1":
        for field in (
            "multi_source_answer",
            "multi_source_attribute",
            "multi_source_long_answer",
        ):
            if not answers or not answers[0].get(field):
                failures.append(f"MISSING_MULTI_SOURCE: answers[0] lacks {field}")

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
    """Stratified sample by tid (one question family each)."""
    by_tid: dict[str, list] = {}
    for e in entries:
        by_tid.setdefault(e.get("tid") or e.get("type", "unknown"), []).append(e)
    sample = []
    for group in by_tid.values():
        k = max(1, int(len(group) * rate))
        sample.extend(random.sample(group, min(k, len(group))))
    return sample


def print_spot_check_tsv(sample: list[dict]):
    """One row per sampled question: full record fields an annotator needs to
    check that the SQL actually answers the Vietnamese question."""
    print("id\ttid\ttype\tquestion\tsql\texpected_answer\tannotation")
    for i, e in enumerate(sample):
        q = e.get("question", "")
        qtype = e.get("type", "")
        sql = e.get("sql", "").replace("\t", " ").replace("\n", " ")
        ans = e.get("answers", [{}])
        ans_name = (
            ans[0].get("poi_name")
            or ans[0].get("road_name")
            or ans[0].get("park_name")
            or ans[0].get("lake_name")
            or str(ans[0])[:60]
            if ans
            else ""
        )
        print(
            f"{e.get('id', i)}\t{e.get('tid', '')}\t{qtype}\t{q}\t{sql}\t{ans_name}\t"
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def load_jsonl(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                entries.append(json.loads(stripped))
    return entries


def verify_file(
    path: Path, spot_rate: float = 0.0, seen_questions: set[str] | None = None
) -> tuple[int, int]:
    """Verify one JSONL file. `seen_questions` carries the dataset-global
    question set so duplicates across files are also caught."""
    entries = load_jsonl(path)
    passed = 0
    failed = 0
    fail_log = []
    if seen_questions is None:
        seen_questions = set()

    for i, entry in enumerate(entries):
        result = run_layer2(entry, i, expected_type=path.stem)
        if entry.get("question") in seen_questions:
            result.failures.append(
                "DUPLICATE: identical question text seen earlier in the dataset"
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
    global_questions: set[str] = set()

    if p.is_dir():
        files = sorted(p.glob("*.jsonl"))
        if not files:
            print(f"No .jsonl files found in {p}")
            sys.exit(1)
        for f in files:
            pp, ff = verify_file(f, args.spot_check, global_questions)
            total_pass += pp
            total_fail += ff
    else:
        total_pass, total_fail = verify_file(p, args.spot_check, global_questions)

    total = total_pass + total_fail
    pct = 100 * total_pass / total if total else 0
    print(f"\n══ TOTAL: {total_pass}/{total} passed ({pct:.1f}%) ══")
    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
