import json
import os
import sys
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
TIMEOUT_SECONDS = 60
MAX_TOOL_CALLS = 10

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a relative path from the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from a relative path from the project root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = """You are a documentation agent for this repository.

Use list_files to discover relevant wiki files, then use read_file to inspect them.
Base your answer only on files you have read.
Always provide a source in the format path#section-anchor.

When you are ready to finish, respond with valid JSON only:
{"answer":"...","source":"wiki/...#section-anchor"}
"""


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


def get_question() -> str:
    if len(sys.argv) < 2:
        raise RuntimeError('Usage: uv run agent.py "Your question here"')
    question = sys.argv[1].strip()
    if not question:
        raise RuntimeError("Question must not be empty")
    return question


def safe_resolve_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Path must be a non-empty string")

    raw = relative_path.strip()
    if Path(raw).is_absolute():
        raise ValueError("Absolute paths are not allowed")

    candidate = (PROJECT_ROOT / raw).resolve()
    root = PROJECT_ROOT.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Access outside project directory is not allowed") from exc

    return candidate


def list_files(path: str) -> str:
    try:
        target = safe_resolve_path(path)
        if not target.exists():
            return f"Error: path does not exist: {path}"
        if not target.is_dir():
            return f"Error: not a directory: {path}"
        return "\n".join(sorted(item.name for item in target.iterdir()))
    except Exception as exc:
        return f"Error: {exc}"


def read_file(path: str) -> str:
    try:
        target = safe_resolve_path(path)
        if not target.exists():
            return f"Error: file does not exist: {path}"
        if not target.is_file():
            return f"Error: not a file: {path}"
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error: {exc}"


def execute_tool(name: str, args: dict[str, Any]) -> str:
    if name == "list_files":
        return list_files(str(args.get("path", "")))
    if name == "read_file":
        return read_file(str(args.get("path", "")))
    return f"Error: unknown tool: {name}"


def extract_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()
    return ""


def parse_final_response(content: str) -> dict[str, str]:
    try:
        data = json.loads(content)
        return {
            "answer": str(data["answer"]).strip(),
            "source": str(data["source"]).strip(),
        }
    except Exception:
        return {
            "answer": content.strip() or "No answer produced.",
            "source": "unknown",
        }


def load_mock_responses() -> list[dict[str, Any]] | None:
    raw = os.getenv("MOCK_LLM_RESPONSES")
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise RuntimeError("MOCK_LLM_RESPONSES must be a JSON list")
    return parsed


def call_llm(
    messages: list[dict[str, Any]],
    api_key: str,
    api_base: str,
    model: str,
    mock_state: dict[str, Any] | None,
) -> dict[str, Any]:
    if mock_state is not None:
        index = mock_state["index"]
        responses = mock_state["responses"]
        if index >= len(responses):
            raise RuntimeError("Ran out of mock LLM responses")
        mock_state["index"] += 1
        return responses[index]

    url = f"{api_base.rstrip('/')}/chat/completions"
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0,
        },
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    try:
        question = get_question()

        api_key = os.getenv("LLM_API_KEY")
        api_base = os.getenv("LLM_API_BASE")
        model = os.getenv("LLM_MODEL")
        if not api_key or not api_base or not model:
            raise RuntimeError("Missing required environment variables: LLM_API_KEY, LLM_API_BASE, LLM_MODEL")

        mock_responses = load_mock_responses()
        mock_state = None if mock_responses is None else {"responses": mock_responses, "index": 0}

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        tool_calls_log: list[dict[str, Any]] = []
        final_answer = "No answer produced."
        final_source = "unknown"

        for _ in range(MAX_TOOL_CALLS + 1):
            llm_response = call_llm(messages, api_key, api_base, model, mock_state)
            message = llm_response["choices"][0]["message"]

            assistant_message: dict[str, Any] = {"role": "assistant"}
            if "content" in message:
                assistant_message["content"] = message.get("content", "")
            if "tool_calls" in message:
                assistant_message["tool_calls"] = message["tool_calls"]
            messages.append(assistant_message)

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for tool_call in tool_calls:
                    if len(tool_calls_log) >= MAX_TOOL_CALLS:
                        break

                    function = tool_call.get("function", {})
                    tool_name = function.get("name", "")
                    raw_arguments = function.get("arguments", "{}")

                    try:
                        args = json.loads(raw_arguments)
                        if not isinstance(args, dict):
                            raise ValueError("Arguments must be an object")
                    except Exception as exc:
                        args = {}
                        result = f"Error: invalid tool arguments: {exc}"
                    else:
                        result = execute_tool(tool_name, args)

                    tool_calls_log.append(
                        {"tool": tool_name, "args": args, "result": result}
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": result,
                        }
                    )
                continue

            final = parse_final_response(extract_content(message.get("content", "")))
            final_answer = final["answer"]
            final_source = final["source"]
            break

        print(json.dumps({
            "answer": final_answer,
            "source": final_source,
            "tool_calls": tool_calls_log,
        }, ensure_ascii=False))
        return 0

    except Exception as exc:
        eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
