"""Verify llama.cpp's Qwen runtime alias before official inference."""

import argparse
import json
import urllib.request

RUNTIME = "unsloth/Qwen3.5-9B-GGUF:Q4_K_XL"
HF_REPO = "unsloth/Qwen3.5-9B-GGUF:UD-Q4_K_XL"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models_url")
    args = parser.parse_args()

    with urllib.request.urlopen(args.models_url, timeout=10) as response:
        models = json.load(response).get("data", [])
    model = next((item for item in models if item.get("id") == RUNTIME), None)
    if model is None:
        raise SystemExit(f"runtime alias not advertised: {RUNTIME}")
    server_args = model.get("status", {}).get("args", [])
    if not any(
        server_args[i : i + 2] == ["--hf-repo", HF_REPO]
        for i in range(len(server_args) - 1)
    ):
        raise SystemExit(f"{RUNTIME} does not resolve to {HF_REPO}")
    print(f"[INFO] {RUNTIME} -> {HF_REPO}")


if __name__ == "__main__":
    main()
