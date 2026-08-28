"""GS-QA baselines: upstream pipeline plus the Vietnamese patch layer.

A top-level package of the ViGSQA distribution so the notebook can import the
patched pipeline in-process instead of reaching for `sys.path` hacks. Run the
Vietnamese CLI from the repo root with `python -m baselines.baselines_vi`;
artifacts (caches, eval CSVs) stay inside this directory.
"""
