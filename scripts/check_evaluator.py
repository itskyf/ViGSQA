#!/usr/bin/env python3
"""Focused offline checks for the ViGSQA v3 evaluator contract."""

import json
import tempfile
import unicodedata
from pathlib import Path

from geopy.exc import GeocoderQueryError, GeocoderUnavailable
from geopy.extra.rate_limiter import RateLimiter
from run_evaluation import (
    best_error,
    best_text,
    evaluate,
    finite_number,
    load_geocodes,
    normalize_text,
    validate_questions,
)

from baselines import pipeline
from baselines.baselines_vi import INFERENCE_PROFILE
from vigsqa.sealing import (
    EVALUATION_PARSER_MAX_ATTEMPTS,
    EVALUATION_PARSER_MODEL,
    EVALUATION_PARSER_PROFILE,
    EVALUATION_PARSER_PROMPT,
    evaluation_parser_identity,
)


class Location:
    latitude = 10.0
    longitude = 106.0


class Geocoder:
    def geocode(self, address, exactly_one=True):
        assert address == "1 Đường Mới, Hà Nội"
        assert exactly_one is True
        return Location()


# Mirrors the production RateLimiter(max_retries=2) in run_evaluation.py.
MAX_RETRIES = 2


class FlakyGeocoder:
    """Fail for the full retry budget like a transient outage, then resolve."""

    def __init__(self):
        self.calls = 0

    def __call__(self, address, exactly_one=True):
        self.calls += 1
        if self.calls <= MAX_RETRIES:
            raise GeocoderUnavailable("service unavailable")
        return Location()


def unavailable_geocode(address, exactly_one=True):
    raise GeocoderUnavailable("service unavailable")


def rejected_geocode(address, exactly_one=True):
    raise GeocoderQueryError("Non-successful status code 400")


def uncalled_geocode(address, exactly_one=True):
    raise AssertionError("cached records must not be re-queried")


def fast_rate_limiter(func):
    """Production-shaped limiter with near-zero delays for offline checks."""
    return RateLimiter(
        func,
        min_delay_seconds=0,
        max_retries=MAX_RETRIES,
        error_wait_seconds=0.01,
        swallow_exceptions=False,
    )


def main() -> None:
    evaluated_models = (
        "ornith-ai/Ornith-1.5-9B-NVFP4",
        "AxionML/Qwen3.5-9B-NVFP4",
    )
    parser_identities = {
        (model, baseline): evaluation_parser_identity()
        for model in evaluated_models
        for baseline in ("direct", "text2sql")
    }
    assert (
        len({json.dumps(value, sort_keys=True) for value in parser_identities.values()})
        == 1
    )
    parser_identity = next(iter(parser_identities.values()))
    assert parser_identity["model"] == EVALUATION_PARSER_MODEL == evaluated_models[0]
    assert parser_identity["prompt"] == EVALUATION_PARSER_PROMPT
    assert parser_identity["profile"] == EVALUATION_PARSER_PROFILE
    assert EVALUATION_PARSER_PROFILE == INFERENCE_PROFILE
    assert parser_identity["max_attempts"] == EVALUATION_PARSER_MAX_ATTEMPTS
    evaluation_runner = (pipeline.ROOT.parent / "scripts" / "evaluate.sh").read_text()
    assert f'PARSER_MODEL="{EVALUATION_PARSER_MODEL}"' in evaluation_runner

    composed = "Đường Trần Hưng Đạo, số 12!"
    decomposed = unicodedata.normalize("NFD", composed)
    assert normalize_text(composed) == normalize_text(decomposed)
    assert normalize_text(composed) == "đường trần hưng đạo số 12"
    assert finite_number("1.5 km", "distance") == 1.5 * 1000
    assert finite_number("2 ha", "area") == 2 * 10_000
    assert finite_number("1.5", "count") is None
    angle, _, _ = best_error([359], [1], "direction")
    assert angle == {"attempted": True, "error": 2 / 180}
    text, prediction, gold = best_text(["đáp án hai"], ["sai", "đáp án hai"])
    assert text["f1"] == 1 and (prediction, gold) == (0, 1)
    text, prediction, gold = best_text(["Hồ Tây"], [])
    assert text["f1"] == 0 and text["attempted"] is False
    assert (prediction, gold) == (None, None)

    question = {
        "id": "range+loc-check",
        "tid": "T13",
        "type": "range+loc",
        "answers": [
            {"address": "xa", "geo_wkt": "POINT(100 20)"},
            {"address": "1 Đường Mới, Hà Nội", "geo_wkt": "POINT(106 10)"},
        ],
    }
    parsed = {
        "id": question["id"],
        "content": '```json\n{"address": "1 Đường Mới, Hà Nội"}\n```',
    }
    with tempfile.TemporaryDirectory() as directory:
        geocodes = load_geocodes(
            Path(directory) / "geocodes.json",
            ["1 Đường Mới, Hà Nội"],
            Geocoder().geocode,
        )
    row = evaluate([question], [parsed], geocodes)[0]
    assert row["metrics"]["spatial"] == {"attempted": True, "error": 0.0}
    assert row["selected"]["spatial"]["gold"] == 1

    # Lake-name golds (T11/T12) are entity golds too; they previously fell
    # through the entity key set and crashed scoring with empty golds.
    lake_row = evaluate(
        [
            {
                "id": "lake-check",
                "tid": "T11",
                "type": "intersects:area_max+name",
                "answers": [
                    {"lake_name": "Hồ Tây", "area": 5.0, "geo_wkt": "POINT(105 21)"}
                ],
            }
        ],
        [{"id": "lake-check", "content": '```json\n{"name": "Hồ Tây"}\n```'}],
        [],
    )[0]
    assert lake_row["metrics"]["text"] == {
        "attempted": True,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }

    # A rate-limited geocoder retries transient failures; once retries are
    # exhausted the run aborts without recording not_found for the address.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "geocodes.json"
        geocodes = load_geocodes(
            path, ["1 Đường Mới, Hà Nội"], fast_rate_limiter(FlakyGeocoder())
        )
        assert geocodes[0]["status"] == "found"
        try:
            load_geocodes(
                path, ["2 Đường Cũ, Hà Nội"], fast_rate_limiter(unavailable_geocode)
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("exhausted retries must abort the evaluation")
        assert json.loads(path.read_text()) == geocodes
        # A rejected query (HTTP 400) is a terminal negative: persisted with a
        # reason, distinct from a confirmed not_found, and never re-queried.
        blob = "2 Đường Cũ, Hà Nội; 3 Đường Hết, Hà Nội"
        assert load_geocodes(path, [blob], fast_rate_limiter(rejected_geocode)) == [
            {
                "address": blob,
                "status": "rejected",
                "reason": "Non-successful status code 400",
            }
        ]
        assert load_geocodes(path, [blob], fast_rate_limiter(uncalled_geocode)) == [
            {
                "address": blob,
                "status": "rejected",
                "reason": "Non-successful status code 400",
            }
        ]
        rejected_row = evaluate(
            [
                {
                    "id": "rejected-check",
                    "tid": "T13",
                    "type": "range+loc",
                    "answers": [{"address": "xa", "geo_wkt": "POINT(100 20)"}],
                }
            ],
            [
                {
                    "id": "rejected-check",
                    "content": f'```json\n{{"address": "{blob}"}}\n```',
                }
            ],
            [{"address": blob, "status": "rejected", "reason": "status code 400"}],
        )[0]
        assert rejected_row["metrics"]["spatial"] == {"attempted": False, "error": 1.0}

    questions = pipeline.load_questions("full")
    validate_questions(questions)
    print("evaluator contract checks passed")


if __name__ == "__main__":
    main()
