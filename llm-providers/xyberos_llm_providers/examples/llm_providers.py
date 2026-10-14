"""Example (M6): configure any LLM provider by name.

Lists the OpenAI-compatible presets and runs one configured provider. Use
``--stub`` for a no-network demo (a fake transport returns a canned response);
without it, a real API call is made (set the provider's API key env var):

    python examples/llm_providers.py --provider groq --stub
    # real call: export GROQ_API_KEY=... ; python examples/llm_providers.py --provider groq
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from xyberos_llm_providers import get_llm, list_presets


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure an LLM provider by name")
    parser.add_argument("--provider", default="groq")
    parser.add_argument("--prompt", default="Say hello in one short sentence.")
    parser.add_argument("--stub", action="store_true", help="use a fake transport (no network)")
    args = parser.parse_args()

    print("available presets:", ", ".join(list_presets()))

    if args.stub:
        def post(url, payload, headers):
            return {"choices": [{"message": {"content": f"[stub] would POST to {url}"}}]}
        llm = get_llm(args.provider, api_key="stub", post=post)
    else:
        llm = get_llm(args.provider)  # API key from <PROVIDER>_API_KEY env

    print(f"\n{args.provider} -> {llm.generate(args.prompt)}")


if __name__ == "__main__":
    main()
