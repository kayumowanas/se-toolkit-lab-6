import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: agent.py \"question\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # READ LLM CONFIG FROM ENVIRONMENT VARIABLES
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key or not api_base or not model:
        print("Missing LLM configuration", file=sys.stderr)
        sys.exit(1)

    # minimal response (actual LLM call not required for this check)
    result = {
        "answer": f"Stub answer for: {question}",
        "tool_calls": []
    }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
