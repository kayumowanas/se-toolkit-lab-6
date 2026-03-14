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
            "description": (
                "List files and directories at a relative path from the project root. "
                "Use this to discover wiki files, backend modules, router files, ETL code, "
                "and Docker-related files before reading them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from the project root.",
                    }
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
            "description": (
                "Read a file from a relative path from the project root. "
                "Use this for wiki questions, source code questions, Docker questions, "
                "request lifecycle analysis, ETL behavior, and bug diagnosis from code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path from the project root.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": (
                "Call the running backend API for live system facts or data-dependent "
                "questions. Use this for item counts, authentication behavior, status codes, "
                "analytics results, endpoint errors, and other runtime questions. "
                "For debugging endpoint failures, query the API first, then read source code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method such as GET, POST, PUT, PATCH, or DELETE.",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "API path beginning with /. Example: /items/ or "
                            "/analytics/completion-rate?lab=lab-99"
                        ),
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Optional JSON request body encoded as a string. "
                            "Omit this for GET requests."
                        ),
                    },
                },
                "required": ["method", "path"],
                "additionalProperties": False,
            },
        },
    },
]


SYSTEM_PROMPT = """You are a system agent for this repository.

You can answer questions using:
- wiki and documentation files,
- source code in the repository,
- the live backend API.

Tool selection rules:
- Use list_files to discover relevant files and directories.
- Use read_file for wiki questions, source code questions, Docker/deployment questions, request lifecycle explanations, ETL behavior, and bug diagnosis from code.
- Use query_api for live system questions, runtime behavior, item counts, status codes, analytics results, authentication behavior, and endpoint failures.
- For debugging questions, first query the failing API endpoint, then read the relevant source code to explain the bug.
- Prefer the real running system over documentation when the question asks about current data or runtime behavior.
- Do not invent facts not grounded in tool results.
- Keep answers concise but specific.
- Mention the exact error when diagnosing API failures.

If the answer comes from a file, include a source in the format path#section-anchor when possible.
If the answer comes from the live system and no file source is needed, source may be omitted.

When you are ready to finish, respond with valid JSON only in one of these forms:
{"answer":"...","source":"path#anchor"}
{"answer":"..."}
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

        entries = sorted(item.name for item in target.iterdir())
        return "\n".join(entries)
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


def query_api(method: str, path: str, body: str | None = None) -> str:
    try:
        lms_api_key = os.getenv("LMS_API_KEY")
        if not lms_api_key:
            return "Error: missing LMS_API_KEY"

        base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002").rstrip("/")

        if not isinstance(method, str) or not method.strip():
            return "Error: method must be a non-empty string"
        if not isinstance(path, str) or not path.strip():
            return "Error: path must be a non-empty string"
        if not path.startswith("/"):
            return "Error: path must start with /"

        url = f"{base_url}{path}"
        headers = {
            "Authorization": f"Bearer {lms_api_key}",
            "Content-Type": "application/json",
        }

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": TIMEOUT_SECONDS,
        }

        if body is not None and body != "":
            try:
                request_kwargs["json"] = json.loads(body)
            except json.JSONDecodeError as exc:
                return f"Error: body is not valid JSON: {exc}"

        response = requests.request(
            method=method.upper(),
            url=url,
            **request_kwargs,
        )

        try:
            parsed_body = response.json()
        except ValueError:
            parsed_body = response.text

        return json.dumps(
            {
                "status_code": response.status_code,
                "body": parsed_body,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return f"Error: {exc}"


def execute_tool(name: str, args: dict[str, Any]) -> str:
    if name == "list_files":
        return list_files(str(args.get("path", "")))
    if name == "read_file":
        return read_file(str(args.get("path", "")))
    if name == "query_api":
        body = args.get("body")
        return query_api(
            method=str(args.get("method", "")),
            path=str(args.get("path", "")),
            body=None if body is None else str(body),
        )
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
        answer = str(data["answer"]).strip()
        source = str(data.get("source", "")).strip()

        return {
            "answer": answer or "No answer produced.",
            "source": source,
        }
    except Exception:
        return {
            "answer": content.strip() or "No answer produced.",
            "source": "",
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
            raise RuntimeError(
                "Missing required environment variables: "
                "LLM_API_KEY, LLM_API_BASE, LLM_MODEL"
            )

        mock_responses = load_mock_responses()
        mock_state = None
        if mock_responses is not None:
            mock_state = {
                "responses": mock_responses,
                "index": 0,
            }

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        tool_calls_log: list[dict[str, Any]] = []
        final_answer = "No answer produced."
        final_source = ""

        for _ in range(MAX_TOOL_CALLS + 1):
            llm_response = call_llm(
                messages=messages,
                api_key=api_key,
                api_base=api_base,
                model=model,
                mock_state=mock_state,
            )

            try:
                message = llm_response["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Unexpected LLM response format: {llm_response}"
                ) from exc

            assistant_message: dict[str, Any] = {"role": "assistant"}

            if "content" in message:
                assistant_message["content"] = message.get("content") or ""
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
                        {
                            "tool": tool_name,
                            "args": args,
                            "result": result,
                        }
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": result,
                        }
                    )

                continue

            final = parse_final_response(extract_content(message.get("content") or ""))
            final_answer = final["answer"]
            final_source = final["source"]
            break

        result: dict[str, Any] = {
            "answer": final_answer,
            "tool_calls": tool_calls_log,
        }

        if final_source:
            result["source"] = final_source

        print(json.dumps(result, ensure_ascii=False))
        return 0

    except Exception as exc:
        eprint(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
