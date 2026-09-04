#!/usr/bin/env python3
"""Focused offline checks for the ViGSQA v3 evaluator contract."""

import json
import tempfile
import unicodedata
from pathlib import Path

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
            Geocoder(),
        )
    row = evaluate([question], [parsed], geocodes)[0]
    assert row["metrics"]["spatial"] == {"attempted": True, "error": 0.0}
    assert row["selected"]["spatial"]["gold"] == 1

    questions = pipeline.load_questions("full")
    validate_questions(questions)
    print("evaluator contract checks passed")


if __name__ == "__main__":
    main()
