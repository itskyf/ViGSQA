#!/usr/bin/env python3
"""Run only the raw stages of an official Vietnamese baseline."""

import argparse
from contextlib import ExitStack

from langchain_openai import ChatOpenAI

from baselines import pipeline
from baselines.baselines_vi import build_model_vi, setup_llm_cache


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--baseline", required=True, choices=("direct", "text2sql"))
    parser.add_argument("--mode", required=True, choices=("smoke", "full"))
    parser.add_argument("--llm-concurrency", required=True, type=int)
    args = parser.parse_args()
    if args.llm_concurrency < 1:
        parser.error("--llm-concurrency must be at least 1")

    setup_llm_cache()
    model = build_model_vi(args.model)
    questions = pipeline.load_questions(args.mode)
    print(f"Model: {args.model}  |  Baseline: {args.baseline}")
    print(f"Loaded {len(questions)} questions from {pipeline.QUESTIONS_DIR}")

    with ExitStack() as clients:
        if isinstance(model, ChatOpenAI):
            clients.enter_context(model.root_client)
        if args.baseline == "direct":
            pipeline.step_generate_answers(
                questions,
                model,
                args.model,
                cache_key="direct_answer",
                system_prompt=pipeline.load_prompt("direct_answer"),
                llm_concurrency=args.llm_concurrency,
            )
        else:
            generated = pipeline.step_generate_answers(
                questions,
                model,
                args.model,
                cache_key="sql_generate",
                system_prompt=pipeline.load_prompt("sql_generate"),
                llm_concurrency=args.llm_concurrency,
            )
            executed = pipeline.step_execute_sql(
                questions,
                generated,
                args.model,
                sql_concurrency=max(
                    args.llm_concurrency, pipeline.DEFAULT_SQL_CONCURRENCY
                ),
            )
            pipeline.step_answer_from_records(
                questions,
                generated,
                executed,
                model,
                args.model,
                llm_concurrency=args.llm_concurrency,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
