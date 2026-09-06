"""T09: cache-key probe + prune/migrate/validate/concurrency checks for the
sql_generate cache.

Stages (each runs the probe checks first — the probe is the blocker gate):
  --probe       cache-key semantics check against in-memory SQLite (P1-P4)
  --prune       drop the empty-content records from sql_generate.json (1564 → 1513)
  --migrate     insert the healthy records into the PostgreSQL LangChain cache
  --validate    replay every migrated id through the cache with `_generate`
                monkeypatched to raise: the original base_url and a dead
                base_url must both hit byte-identically, a changed model
                name must miss
  --concurrency bounded-concurrency acceptance through invoke_or_capture_many

Everything reuses the production code paths (baselines_vi patches, pipeline
loaders, TransportNormalizedMd5Cache) so cache keys are correct by construction
and normalization lives in exactly one place. No model is ever called: the
replay raises on any miss, so a wrong key surfaces loudly instead of silently
re-running inference.

Usage (repo root):
    python scripts/migrate_sql_generate_cache.py --<stage>
"""

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_core.caches import BaseCache
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration
from langchain_openai import ChatOpenAI
from sqlalchemy import create_engine, text

# `baselines` ships with the distribution (editable install), so this script
# imports it from any cwd without path manipulation; importing baselines_vi
# applies the VN patches (QUESTIONS_DIR, CACHE_DIR, prompts, model routing).
import baselines.baselines_vi as vi
from baselines import pipeline

ROOT = Path(__file__).resolve().parent.parent

MODEL = "llamacpp:ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M"
BACKUP = ROOT / "logs" / "official" / "pre_t09_sql_generate_1564.json"
EXPECTED_EMPTY = 51
DEAD_URL = "http://127.0.0.1:9"  # nothing listens; a real call would fail loudly


class _RecordingCache(BaseCache):
    """Capture the exact (prompt, llm_string) LangChain derives inside invoke()."""

    def __init__(self):
        self.keys = []

    def lookup(self, prompt, llm_string):
        self.keys.append((prompt, llm_string))

    def update(self, prompt, llm_string, return_val):
        pass

    def clear(self):
        pass


class _NoModel:
    """Stand-in for `model._generate`: any real call raises loudly."""

    def __init__(self, why):
        self.why = why

    def __call__(self, *args, **kwargs):
        raise RuntimeError(self.why)


def _build_model(base_url=None, model_name=None):
    """A ChatOpenAI built exactly like a real run (base_url in the key)."""
    if base_url is not None:
        previous = os.environ.get("LLAMACPP_URL")
        os.environ["LLAMACPP_URL"] = base_url
        try:
            return vi._build_model_vi(model_name or MODEL)
        finally:
            if previous is None:
                del os.environ["LLAMACPP_URL"]
            else:
                os.environ["LLAMACPP_URL"] = previous
    return vi._build_model_vi(model_name or MODEL)


def _captured_key(messages, base_url=None):
    """Derive (prompt, llm_string) for `messages` without touching any model."""
    model = _build_model(base_url=base_url)
    model.cache = _RecordingCache()
    model._generate = _NoModel("offline key capture: no model calls")
    try:
        model.invoke(messages)
    except RuntimeError as e:
        if "offline key capture" not in str(e):
            raise
    return model.cache.keys[-1]


def healthy_records() -> list[dict]:
    """The non-empty sql_generate records, in file order."""
    path = pipeline.cache_path(MODEL, "sql_generate")
    records = json.loads(path.read_text())
    return [r for r in records if r.get("content")]


def _generate_messages(questions_by_id, record):
    q = questions_by_id[record["id"]]
    return [
        SystemMessage(content=pipeline.load_prompt("sql_generate")),
        HumanMessage(content=q["question"]),
    ]


# ---------------------------------------------------------------------------
# Probe: the cache-key contract (docs/plans/T09-llm-cache-postgres.md)
# ---------------------------------------------------------------------------


def probe() -> None:
    """P1-P4 against in-memory SQLite — no Postgres, no llama.cpp, no JSON.

    P1 documents that native keys are transport-coupled (why the normalized
    class exists); P2-P4 prove the normalization honors the contract: same
    semantic request across endpoints → one row; different model/generation
    semantics → separate rows.
    """
    msgs = [SystemMessage(content="SYS"), HumanMessage(content="Q")]
    content = "```sql\nSELECT 1;\n```"

    def chat(**over):
        params = dict(
            model="ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M",
            base_url="http://127.0.0.1:8000/v1",
            api_key="not-needed",
            temperature=0,
            max_tokens=4096,
        )
        params.update(over)
        return ChatOpenAI(**params)

    # P1: native keys embed the endpoint (the incompatibility being fixed).
    a, b = chat(), chat(base_url="http://10.0.0.1:8000/v1")
    assert a._get_llm_string() != b._get_llm_string(), (
        "P1: expected native llm_strings to differ across base_url"
    )
    print("  P1 ok: native keys differ across base_url (transport-coupled)")

    # P2: normalization removes endpoint/api-key identity.
    c = chat(api_key="sk-something-else")
    n_a = vi._normalize_llm_string(a._get_llm_string())
    assert n_a == vi._normalize_llm_string(b._get_llm_string()), "P2: base_url leaked"
    assert n_a == vi._normalize_llm_string(c._get_llm_string()), "P2: api_key leaked"
    print("  P2 ok: normalized keys equal across base_url and api_key")

    cache = vi.TransportNormalizedMd5Cache(create_engine("sqlite://"))

    # P3: cross-endpoint reuse — store under A's key, read from B's.
    prompt_a, llm_a = _captured_key(msgs, base_url="http://127.0.0.1:8000")
    cache.update(prompt_a, llm_a, [ChatGeneration(message=AIMessage(content=content))])
    hit = chat(base_url="http://10.0.0.1:8000/v1")
    hit.cache = cache
    hit._generate = _NoModel("P3 miss: cross-endpoint lookup failed")
    assert hit.invoke(msgs).content == content, "P3: content not byte-identical"
    print("  P3 ok: endpoint B hits the row stored via endpoint A")

    # P4: model/generation changes must miss (fresh construction, not mutation).
    for label, over in (
        ("model name", {"model": "unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL"}),
        ("temperature", {"temperature": 0.7}),
    ):
        miss = chat(base_url="http://10.0.0.1:8000/v1", **over)
        miss.cache = cache
        miss._generate = _NoModel(f"P4 {label} change unexpectedly hit")
        try:
            miss.invoke(msgs)
        except RuntimeError as e:
            assert f"P4 {label}" in str(e), f"P4: wrong failure for {label}: {e}"
        else:
            raise AssertionError(f"P4: {label} change must miss, got a hit")
        assert vi._normalize_llm_string(miss._get_llm_string()) != n_a, (
            f"P4: normalized key unchanged after {label} change"
        )
        print(f"  P4 ok: {label} change misses")

    print("[probe] cache-key contract verified.")


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def prune() -> None:
    """Drop empty-content records (targeted prune, never --clear-cache)."""
    assert BACKUP.is_file(), (
        f"refusing to prune: backup missing at {BACKUP} (Phase 0 first)"
    )
    path = pipeline.cache_path(MODEL, "sql_generate")
    records = json.loads(path.read_text())
    healthy = [r for r in records if r.get("content")]
    empty = [r for r in records if not r.get("content")]
    assert not any(r.get("error") for r in empty), (
        "unexpected error records in the prune set — review before pruning"
    )
    assert len(records) - len(healthy) == EXPECTED_EMPTY, (
        f"expected {EXPECTED_EMPTY} empty records, found {len(records) - len(healthy)}"
    )
    pipeline.save_cache(MODEL, "sql_generate", healthy)
    print(
        f"[prune] {len(records)} -> {len(healthy)} records"
        f" ({len(empty)} empties dropped: {[r['id'] for r in empty]})"
    )


def migrate() -> None:
    """Insert every healthy record into the PostgreSQL cache (idempotent)."""
    questions_by_id = {q["id"]: q for q in pipeline.load_questions()}
    records = healthy_records()
    assert records, "nothing to migrate"
    cache = vi.TransportNormalizedMd5Cache(vi.llm_cache_engine())
    for record in records:
        prompt, llm_string = _captured_key(_generate_messages(questions_by_id, record))
        cache.update(
            prompt,
            llm_string,
            [ChatGeneration(message=AIMessage(content=record["content"]))],
        )
    _assert_row_counts(cache.engine, len(records))
    print(f"[migrate] {len(records)} records in the PostgreSQL cache")


def _assert_row_counts(engine, expected: int) -> None:
    with engine.connect() as conn:
        total, distinct = conn.execute(
            text("SELECT count(*), count(DISTINCT prompt) FROM full_md5_llm_cache")
        ).one()
    assert total == expected, f"expected {expected} rows, found {total}"
    assert distinct == expected, (
        f"expected {expected} distinct prompts, found {distinct}"
    )
    print(f"  rows: {total}, distinct prompts: {distinct}")


def validate() -> None:
    """Replay all healthy ids through the cache — hits must be byte-identical."""
    questions_by_id = {q["id"]: q for q in pipeline.load_questions()}
    records = healthy_records()
    cache = vi.TransportNormalizedMd5Cache(vi.llm_cache_engine())
    _assert_row_counts(cache.engine, len(records))

    def replay(base_url, label):
        model = _build_model(base_url=base_url)
        model.cache = cache
        why = f"{label}: cache miss"
        for i, record in enumerate(records):
            model._generate = _NoModel(f"{why} (id {record['id']})")
            try:
                out = model.invoke(_generate_messages(questions_by_id, record))
            except RuntimeError as e:
                raise SystemExit(f"[validate] FAIL at record {i}: {e}") from e
            assert out.content == record["content"], (
                f"[validate] FAIL: content mismatch for {record['id']} ({label})"
            )
        print(f"[validate] {len(records)}/{len(records)} byte-identical hits ({label})")

    replay(None, "original LLAMACPP_URL")
    replay(DEAD_URL, "dead base_url")

    # Model-sensitivity control: only the model name changed → must miss.
    control = _build_model(
        base_url=DEAD_URL,
        model_name="llamacpp:unsloth/Qwen3.5-9B-MTP-GGUF:UD-Q4_K_XL",
    )
    control.cache = cache
    control._generate = _NoModel("model change unexpectedly hit")
    try:
        control.invoke(_generate_messages(questions_by_id, records[0]))
    except RuntimeError as e:
        assert "model change" in str(e), f"unexpected failure: {e}"
    else:
        raise SystemExit("[validate] FAIL: model-name change must miss")
    print("[validate] model-name control misses as required")
    print("[validate] cache-key contract holds end to end.")


def concurrency() -> None:
    """Offline bounded-concurrency acceptance — no llama.cpp, no official run.

    Replays a sample of migrated prompts through the production
    `invoke_or_capture_many` path, observing concurrency via a counting lookup
    subclass of the production cache class:
      - N=1 behaves like the sequential path (observed concurrency exactly 1);
      - N=4 stays bounded (observed > 1 and <= 4) with identical outputs;
      - concurrent idempotent cache writes (N=4) neither corrupt nor duplicate
        rows (count/distinct-prompt unchanged).
    """
    questions_by_id = {q["id"]: q for q in pipeline.load_questions()}
    records = healthy_records()[:64]
    engine = vi.llm_cache_engine()

    lock = threading.Lock()
    counter = {"active": 0, "max": 0}
    probe_limit = 4

    class CountingCache(vi.TransportNormalizedMd5Cache):
        """Production lookup with concurrency observation (super() does the work)."""

        def lookup(self, prompt, llm_string):
            with lock:
                counter["active"] += 1
                counter["max"] = max(counter["max"], counter["active"])
            time.sleep(0.02)  # widen the window so overlap is observable
            try:
                return super().lookup(prompt, llm_string)
            finally:
                with lock:
                    counter["active"] -= 1

    def replay(limit, label):
        counter.update(active=0, max=0)
        model = _build_model(base_url=DEAD_URL)
        model.cache = CountingCache(engine)
        model._generate = _NoModel(f"{label}: cache miss")
        calls = [_generate_messages(questions_by_id, r) for r in records]
        for record, out in zip(
            records,
            pipeline.invoke_or_capture_many(model, calls, llm_concurrency=limit),
            strict=True,
        ):
            assert out[1] is None, f"{label}: miss/error for {record['id']}: {out[1]}"
            assert out[0] == record["content"], (
                f"{label}: content mismatch for {record['id']}"
            )
        print(
            f"[concurrency] N={limit}: {len(records)}/{len(records)} byte-identical"
            f" hits, observed concurrency {counter['max']}"
        )
        return counter["max"]

    # N=4 first: the shared pool is created once at the higher bound; the N=1
    # replay takes the plain sequential branch and never touches the pool.
    max4 = replay(probe_limit, "bounded")
    assert 1 < max4 <= probe_limit, f"expected overlap within the bound, got {max4}"
    max1 = replay(1, "sequential")
    assert max1 == 1, f"sequential path observed concurrency {max1}"

    # Concurrent idempotent writes: re-update a sample exactly like --migrate.
    sample = records[:16]
    keys = [(_captured_key(_generate_messages(questions_by_id, r)), r) for r in sample]
    cache = vi.TransportNormalizedMd5Cache(engine)
    with ThreadPoolExecutor(max_workers=probe_limit) as pool:
        for (prompt, llm_string), record in keys:
            pool.submit(
                cache.update,
                prompt,
                llm_string,
                [ChatGeneration(message=AIMessage(content=record["content"]))],
            )
    _assert_row_counts(engine, len(healthy_records()))
    print("[concurrency] concurrent writes left the cache intact.")


def main() -> None:
    stages = {
        "probe": probe,
        "prune": prune,
        "migrate": migrate,
        "validate": validate,
        "concurrency": concurrency,
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe", action="store_true", help="verify the cache-key contract (P1-P4)"
    )
    parser.add_argument(
        "--prune", action="store_true", help="drop empty-content records"
    )
    parser.add_argument(
        "--migrate", action="store_true", help="insert healthy records into PostgreSQL"
    )
    parser.add_argument(
        "--validate", action="store_true", help="replay ids through the cache"
    )
    parser.add_argument(
        "--concurrency",
        action="store_true",
        help="offline bounded-concurrency acceptance check",
    )
    args = parser.parse_args()
    selected = [name for name, flag in vars(args).items() if flag and name in stages]
    if len(selected) != 1:
        parser.error(
            "select exactly one of --probe/--prune/--migrate/--validate/--concurrency"
        )

    # Blocker gate: every stage re-runs the probe first (fast, in-memory).
    if selected != ["probe"]:
        probe()
    stages[selected[0]]()


if __name__ == "__main__":
    sys.exit(main())
