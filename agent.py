import json
import os
import sys

import requests


TIMEOUT_SECONDS = 60


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def get_question() -> str:
    if len(sys.argv) < 2:
        raise RuntimeError('Usage: uv run agent.py "Your question here"')

    question = sys.argv[1].strip()
    if not question:
        raise RuntimeError("Question must not be empty")

    return question


def call_llm(question: str, api_key: str, api_base: str, model: str) -> str:
    mock_response = os.getenv("MOCK_LLM_RESPONSE")
    if mock_response is not None:
        return mock_response.strip()

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise and helpful assistant. Answer the user's question directly.",
            },
            {
                "role": "user",
                "content": question,
            },
        ],
        "temperature": 0,
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM response format: {data}") from exc

    if isinstance(content, str):
        answer = content.strip()
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        answer = "".join(parts).strip()
    else:
        raise RuntimeError("LLM response content is not a string")

    if not answer:
        raise RuntimeError("LLM returned an empty answer")

    return answer


def main() -> int:
    try:
        question = get_question()

        api_key = os.getenv("LLM_API_KEY")
        api_base = os.getenv("LLM_API_BASE")
        model = os.getenv("LLM_MODEL")

        if not api_key or not api_base or not model:
            raise RuntimeError("Missing required environment variables: LLM_API_KEY, LLM_API_BASE, LLM_MODEL")

        answer = call_llm(question, api_key, api_base, model)

        print(json.dumps({"answer": answer, "tool_calls": []}, ensure_ascii=False))
        return 0
    except Exception as exc:
        eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())