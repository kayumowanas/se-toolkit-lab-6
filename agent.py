import json
import os
import sys

def main() -> int:
    if len(sys.argv) < 2:
        print("Missing question", file=sys.stderr)
        return 1

    question = sys.argv[1]

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key or not api_base or not model:
        print("Missing LLM_API_KEY, LLM_API_BASE, or LLM_MODEL", file=sys.stderr)
        return 1

    result = {
        "answer": f"Stub answer for: {question}",
        "tool_calls": [],
    }
    print(json.dumps(result))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())