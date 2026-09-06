#!/usr/bin/env python3
"""Fresh Vietnamese demo questions: novel anchors, Ornith runs.

Five questions that do not exist in the benchmark, phrased with the
generator's template dialect and anchored on POIs whose names appear
nowhere in the 2,800 benchmark surfaces (asserted). Grounded gold comes
from executing gold SQL read-only.

Model generations replay through the pipeline's resume layer — with no
global LangChain cache configured, the JSON step records under the demo
cache ARE the skip layer (the exact upstream semantics): a question with a
published step record is never re-invoked, and any question without one
attempts the endpoint and fails loudly against the deliberately dead
`OPENAI_BASE_URL`. Step records, not the LangChain cache, are the
cross-platform replay contract: one answer-stage prompt embeds executed
azimuth floats whose rendering differs across distro numeric stacks
(verified: PostgreSQL 18 + PostGIS 3.6 on Ubuntu still differs from the
original Debian-based environment in the last digits), which would change
the prompt bytes and therefore the LangChain cache key. Deterministic
stages — gold SQL, execution of the generated SQL, the records→answer
rescue, presentation — always run live.

The step cache is redirected to `baselines/cache_vi/demo/` — never the
sealed `pv-26b1ac0d` namespace.
"""

import argparse
import json
from contextlib import ExitStack
from pathlib import Path

from langchain_openai import ChatOpenAI
from records_to_answer import canonical_address, exec_rows, rescue_block

from baselines import pipeline
from baselines.baselines_vi import build_model_vi

ROOT = Path(__file__).resolve().parents[1]
MODEL = "ornith-ai/Ornith-1.5-9B-NVFP4"
DEMO_CACHE = ROOT / "baselines" / "cache_vi" / "demo"
OUT_DIR = ROOT / "results" / "demo"

# (question id, family, anchor category filter, target category, template)
SPECS = [
    (
        "demo-001",
        "entity",
        "amenity = 'fast_food'",
        "amenity ILIKE 'pharmacy'",
        "{target_vi} gần {anchor} nhất là gì?",
        "nhà thuốc",
    ),
    (
        "demo-002",
        "location",
        "amenity = 'bank'",
        "tourism ILIKE 'hotel'",
        "Vị trí của {target_vi} gần {anchor} nhất là gì?",
        "khách sạn",
    ),
    (
        "demo-003",
        "count",
        "amenity = 'school'",
        "amenity ILIKE 'fuel'",
        "Có bao nhiêu {target_vi} trong bán kính 5 km quanh {anchor}?",
        "cây xăng",
    ),
    (
        "demo-004",
        "distance",
        "amenity = 'restaurant'",
        "amenity ILIKE 'clinic'",
        "Từ {anchor} đến {target_vi} gần nhất bao xa?",
        "phòng khám",
    ),
    (
        "demo-005",
        "direction",
        "tourism = 'hotel'",
        "amenity ILIKE 'cafe'",
        "Cho tôi biết góc phương vị của các {target_vi} cách {anchor} không quá 3 km.",
        "quán cà phê",
    ),
]


def benchmark_corpus() -> str:
    """All benchmark question surfaces (full + diacritic-stripped) as one text."""
    parts = []
    for path in sorted((ROOT / "generator" / "questions_vi").glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            record = json.loads(line)
            parts.append(record["question_surfaces"]["full"])
            parts.append(record["question_surfaces"]["stripped"])
    return "\n".join(parts)


def novel_anchor(conn, corpus: str, category_filter: str) -> dict:
    """First POI of a category (by id) whose name appears in no surface."""
    rows = pipeline.run_sql(
        "SELECT id, poi_name, ST_AsText(geometry) AS wkt "
        f"FROM pois WHERE {category_filter} AND poi_name IS NOT NULL "
        "ORDER BY id LIMIT 200",
        conn,
    )["output"]
    for row in rows:
        if row["poi_name"] not in corpus:
            return row
    raise SystemExit(f"no novel anchor found for {category_filter!r}")


def _point(wkt: str) -> str:
    return f"ST_GeomFromText('{wkt}',4326)"


def build_demo(conn, corpus: str) -> list[dict]:
    """Five demo questions with generator-dialect gold SQL."""
    demos = []
    for qid, family, anchor_filter, target, template, target_vi in SPECS:
        anchor = novel_anchor(conn, corpus, anchor_filter)
        anchor_point = _point(anchor["wkt"])
        anchor_name = anchor["poi_name"]
        common = f"id <> {anchor['id']} AND {target} AND poi_name IS NOT NULL"
        if family == "entity":
            sql = (
                "SELECT id, geo_wkt, poi_name FROM pois "
                f"WHERE {common} ORDER BY geometry <-> {anchor_point} LIMIT 1;"
            )
        elif family == "location":
            sql = (
                "SELECT id, geo_wkt, poi_name, addr_housenumber, addr_street, "
                "addr_place, addr_suburb, addr_district, addr_city, "
                "addr_province, addr_postcode FROM pois "
                f"WHERE {common} "
                "AND ((addr_street IS NOT NULL OR addr_place IS NOT NULL) "
                "AND (addr_suburb IS NOT NULL OR addr_district IS NOT NULL "
                "OR addr_city IS NOT NULL OR addr_province IS NOT NULL)) "
                f"ORDER BY geometry <-> {anchor_point} LIMIT 1;"
            )
        elif family == "count":
            sql = (
                "SELECT COUNT(*) AS count FROM pois "
                f"WHERE ST_DWithin(geometry, {anchor_point}::geography, 5000) "
                f"AND {common};"
            )
        elif family == "distance":
            sql = (
                "SELECT id, geo_wkt, poi_name, ST_Distance(geometry, "
                f"{anchor_point}::geography) AS distance FROM pois "
                f"WHERE {common} ORDER BY geometry <-> {anchor_point} LIMIT 1;"
            )
        else:  # direction
            sql = (
                "SELECT id, geo_wkt, poi_name, degrees(ST_Azimuth("
                f"{anchor_point}::geography, geometry)) AS angle FROM pois "
                f"WHERE ST_DWithin(geometry, {anchor_point}::geography, 3000) "
                f"AND {common} ORDER BY geometry <-> {anchor_point};"
            )
        question = template.format(anchor=anchor_name, target_vi=target_vi)
        demos.append(
            {
                "id": qid,
                "family": family,
                "question": question,
                "anchor": anchor_name,
                "sql": " ".join(sql.split()),
            }
        )
    return demos


def gold_summary(family: str, rows: list[dict]) -> str:
    if not rows:
        return "∅ (SQL không trả về hàng)"
    if family == "entity":
        return "; ".join(str(row.get("poi_name")) for row in rows[:3])
    if family == "location":
        return "; ".join(
            row.get("address") or canonical_address(row) for row in rows[:1]
        )
    if family == "count":
        return str(rows[0]["count"])
    if family == "distance":
        return f"{rows[0]['distance']:.2f} m"
    return "; ".join(
        f"{row.get('poi_name')}: {row['angle'] % 360:.1f}°" for row in rows[:3]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-concurrency", type=int, default=4)
    args = parser.parse_args()

    corpus = benchmark_corpus()
    conn = pipeline.make_db_conn()
    try:
        demos = build_demo(conn, corpus)
        for demo in demos:
            result = pipeline.run_sql(demo["sql"], conn)
            if result["error"]:
                raise SystemExit(f"gold SQL failed for {demo['id']}: {result['error']}")
            demo["gold_rows"] = result["output"]
            demo["gold"] = gold_summary(demo["family"], result["output"])
    finally:
        conn.close()
    for demo in demos:
        assert demo["anchor"] not in corpus, f"{demo['id']}: anchor not novel"
        assert demo["question"] not in corpus, f"{demo['id']}: question not novel"
    print(
        f"Built {len(demos)} novel demo questions (anchors absent from all "
        f"{len(corpus.splitlines())} benchmark surfaces)."
    )

    # Redirect the cache before any step runs: the default CACHE_DIR is the
    # sealed pv-26b1ac0d namespace and a step write there would invalidate seals.
    DEMO_CACHE.mkdir(parents=True, exist_ok=True)
    pipeline.CACHE_DIR = DEMO_CACHE
    questions = [
        {"id": demo["id"], "question": demo["question"], "type": "demo"}
        for demo in demos
    ]
    model = build_model_vi(MODEL)
    with ExitStack() as clients:
        if isinstance(model, ChatOpenAI):
            clients.enter_context(model.root_client)
        direct = pipeline.step_generate_answers(
            questions,
            model,
            MODEL,
            cache_key="direct_answer",
            system_prompt=pipeline.load_prompt("direct_answer"),
            llm_concurrency=args.llm_concurrency,
        )
        generated = pipeline.step_generate_answers(
            questions,
            model,
            MODEL,
            cache_key="sql_generate",
            system_prompt=pipeline.load_prompt("sql_generate"),
            llm_concurrency=args.llm_concurrency,
        )
        executed = pipeline.step_execute_sql(
            questions, generated, MODEL, sql_concurrency=8
        )
        answered = pipeline.step_answer_from_records(
            questions, generated, executed, model, MODEL, args.llm_concurrency
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Vietnamese demo on fresh questions (Ornith)\n"]
    for demo, direct_row, exec_row, answer_row in zip(
        demos, direct, executed, answered, strict=True
    ):
        rows = exec_rows(exec_row)
        rescue = rescue_block(demo["family"], rows)
        answer_text = (answer_row.get("content") or "").strip()
        rescue_text = ""
        if rescue is not None and not pipeline.extract_json_blocks(answer_text):
            rescue_text = json.dumps(rescue, ensure_ascii=False)
        sql_blocks = exec_row.get("sql_blocks") or []
        demo.update(
            {
                "direct_answer": (direct_row.get("content") or "").strip()[:400],
                "generated_sql": sql_blocks[0] if sql_blocks else None,
                "text2sql_answer": answer_text[:400],
                "rescued": rescue_text,
                "row_count": len(rows),
            }
        )
        lines.append(
            f"<details>\n<summary><code>{demo['id']}</code> · {demo['family']} · "
            f"{demo['row_count']} rows</summary>\n\n"
            f"**Question**\n\n> {demo['question']}\n\n"
            f"**Gold SQL**\n\n```sql\n{demo['sql']}\n```\n\n"
            f"**Generated SQL**\n\n```sql\n{demo['generated_sql'] or '∅'}\n```\n\n"
            f"**Text2SQL answer**\n\n> {demo['text2sql_answer'] or '∅'}\n\n"
            f"**Rescue**\n\n> {demo['rescued'] or '—'}\n\n"
            f"**Gold**\n\n> {demo['gold']}\n\n</details>\n"
        )
    (OUT_DIR / "demo.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_DIR / "demo_results.json").write_text(
        json.dumps(demos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("\n".join(lines))
    print(
        f"\nWrote {OUT_DIR / 'demo.md'} and demo_results.json "
        f"(cache isolated at {DEMO_CACHE})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
