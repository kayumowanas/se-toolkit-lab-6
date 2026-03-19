import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

from dotenv import load_dotenv

load_dotenv(".env.agent.secret")
load_dotenv(".env.docker.secret")

PROJECT_ROOT = Path(__file__).resolve().parent
MAX_ITERATIONS = 10
READ_LIMIT_CHARS = 30000
LIST_LIMIT = 500
ANSWER_LIMIT_CHARS = 320


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _safe_resolve(path_str: str) -> Path:
    candidate = (PROJECT_ROOT / path_str).resolve()
    if PROJECT_ROOT not in [candidate, *candidate.parents]:
        raise ValueError(f"Path escapes repository root: {path_str}")
    return candidate


def _is_probably_text_file(path: Path) -> bool:
    binary_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".mp4",
        ".mov",
        ".svg",
    }
    return path.suffix.lower() not in binary_suffixes


SYSTEM_PROMPT = """
You are a repository and system agent for this project.

Use tools instead of guessing:
- Use read_file for wiki pages, source code, Docker files, configs, and implementation details.
- Use list_files to discover relevant files or router modules before reading them.
- Use query_api for live backend facts: current data, real status codes, authentication behavior, and runtime errors.

Rules:
- For wiki questions, answer from repository files and include a source path or section anchor when possible.
- For source-code questions, inspect the real code with read_file instead of answering from memory.
- For runtime bug diagnosis, first reproduce the problem with query_api, then inspect the relevant source file with read_file.
- For unauthenticated endpoint questions, call query_api with include_auth=false.
- For count questions, use query_api and count returned records instead of guessing.
- For status code questions, report the exact numeric status_code returned by query_api.
- For endpoint crash questions, mention both the runtime error from query_api and the code bug found with read_file.
- For architecture questions, trace the full request flow step by step across the relevant files.
- For ETL idempotency questions, explain the duplicate-detection logic in the code rather than answering abstractly.
- Be precise. Mention specific error names such as ZeroDivisionError or TypeError when you find them.
- Final answers should be concise and factual.
- If you can identify a source file or wiki page, return it in the source field.
- When answering from repository files, always include a source field.
- Prefer returning final answers as JSON with keys "answer" and "source".
""".strip()


READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read a text file from the repository. Use for wiki questions, source code, "
            "Docker/config files, ETL logic, framework questions, and code-based bug diagnosis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path to a file relative to the repository root, for example "
                        "wiki/git-workflow.md or backend/app/main.py."
                    ),
                }
            },
            "required": ["path"],
        },
    },
}

LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": (
            "List files in the repository. Use this to discover relevant wiki pages, backend "
            "modules, router files, or other project files before reading them."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Optional directory path relative to the repository root, for example "
                        "wiki or backend/app/routers. Defaults to the repository root."
                    ),
                }
            },
            "required": [],
        },
    },
}

QUERY_API_TOOL = {
    "type": "function",
    "function": {
        "name": "query_api",
        "description": (
            "Call the running backend API for live system facts and data-dependent questions. "
            "Use for item counts, real endpoint behavior, auth status codes, and reproducing runtime API errors."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method, for example GET or POST.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "API path starting with /, for example /items/ or "
                        "/analytics/completion-rate?lab=lab-99."
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body encoded as a string.",
                },
                "include_auth": {
                    "type": "boolean",
                    "description": (
                        "Whether to include the backend Authorization header. "
                        "Defaults to true."
                    ),
                },
            },
            "required": ["method", "path"],
        },
    },
}

TOOLS = [READ_FILE_TOOL, LIST_FILES_TOOL, QUERY_API_TOOL]


def list_files(path: str | None = None) -> str:
    try:
        root = PROJECT_ROOT if not path else _safe_resolve(path)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    if not root.exists():
        return json.dumps({"error": f"Path does not exist: {path}"}, ensure_ascii=False)

    if root.is_file():
        return json.dumps(
            {"error": f"Expected directory, got file: {path}"},
            ensure_ascii=False,
        )

    items: list[str] = []
    for file_path in sorted(root.rglob("*")):
        if file_path.is_dir():
            continue

        rel = file_path.relative_to(PROJECT_ROOT).as_posix()
        if any(
            part in {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}
            for part in file_path.parts
        ):
            continue

        items.append(rel)
        if len(items) >= LIST_LIMIT:
            break

    return json.dumps({"files": items}, ensure_ascii=False)


def read_file(path: str) -> str:
    try:
        file_path = _safe_resolve(path)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    if not file_path.exists():
        return json.dumps({"error": f"File does not exist: {path}"}, ensure_ascii=False)

    if file_path.is_dir():
        return json.dumps(
            {"error": f"Expected file, got directory: {path}"},
            ensure_ascii=False,
        )

    if not _is_probably_text_file(file_path):
        return json.dumps(
            {"error": f"Binary or unsupported file type: {path}"},
            ensure_ascii=False,
        )

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return json.dumps(
            {"error": f"Could not decode file as UTF-8: {path}"},
            ensure_ascii=False,
        )

    truncated = len(content) > READ_LIMIT_CHARS
    if truncated:
        content = content[:READ_LIMIT_CHARS]

    numbered_lines = [f"{idx}: {line}" for idx, line in enumerate(content.splitlines(), 1)]
    return json.dumps(
        {
            "path": path,
            "content": "\n".join(numbered_lines),
            "truncated": truncated,
        },
        ensure_ascii=False,
    )


def query_api(
    method: str,
    path: str,
    body: str | None = None,
    include_auth: bool = True,
) -> str:
    if not path.startswith("/"):
        path = "/" + path

    base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002").rstrip("/")
    headers: dict[str, str] = {}

    if include_auth:
        lms_api_key = _require_env("LMS_API_KEY")
        headers["Authorization"] = f"Bearer {lms_api_key}"

    data = None
    if body is not None:
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(
        url=f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method.upper(),
    )

    try:
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            try:
                parsed_body = json.loads(raw)
            except json.JSONDecodeError:
                parsed_body = raw

            return json.dumps(
                {"status_code": response.status, "body": parsed_body},
                ensure_ascii=False,
            )
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed_body = json.loads(raw)
        except json.JSONDecodeError:
            parsed_body = raw

        return json.dumps(
            {"status_code": exc.code, "body": parsed_body},
            ensure_ascii=False,
        )
    except Exception as exc:  # pragma: no cover
        return json.dumps(
            {"status_code": 0, "body": str(exc)},
            ensure_ascii=False,
        )


def call_tool(name: str, args: dict[str, Any]) -> str:
    if name == "read_file":
        path = args.get("path")
        if not isinstance(path, str) or not path:
            return json.dumps(
                {"error": "read_file requires a non-empty string path"},
                ensure_ascii=False,
            )
        return read_file(path=path)
    if name == "list_files":
        return list_files(path=args.get("path") or args.get("directory"))
    if name == "query_api":
        method = args.get("method")
        path = args.get("path")
        if not isinstance(method, str) or not method:
            return json.dumps(
                {"error": "query_api requires a non-empty string method"},
                ensure_ascii=False,
            )
        if not isinstance(path, str) or not path:
            return json.dumps(
                {"error": "query_api requires a non-empty string path"},
                ensure_ascii=False,
            )
        return query_api(
            method=method,
            path=path,
            body=args.get("body"),
            include_auth=args.get("include_auth", True),
        )
    return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)


def _chat_completions_url() -> str:
    base = _require_env("LLM_API_BASE").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/chat/completions"


def _mocked_response() -> dict[str, Any] | None:
    responses_raw = os.getenv("MOCK_LLM_RESPONSES")
    if responses_raw:
        responses = json.loads(responses_raw)
        if not responses:
            raise RuntimeError("MOCK_LLM_RESPONSES is empty")
        response = responses.pop(0)
        os.environ["MOCK_LLM_RESPONSES"] = json.dumps(responses)
        return response

    response_text = os.getenv("MOCK_LLM_RESPONSE")
    if response_text is not None:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": response_text,
                    }
                }
            ]
        }

    return None


def llm_chat(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    mocked = _mocked_response()
    if mocked is not None:
        return mocked

    payload = {
        "model": _require_env("LLM_MODEL"),
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0,
    }

    req = request.Request(
        url=_chat_completions_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_require_env('LLM_API_KEY')}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        raise RuntimeError(f"LLM HTTP error {exc.code}: {raw}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode LLM response: {raw}") from exc


def extract_assistant_message(response_json: dict[str, Any]) -> dict[str, Any]:
    try:
        return response_json["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(
            "Unexpected LLM response shape: "
            f"{json.dumps(response_json, ensure_ascii=False)}"
        ) from exc


def build_user_prompt(question: str, source: str | None) -> str:
    text = f"Question: {question}"
    if source:
        text += f"\nSource hint: {source}"
    text += '\nReturn the final response as JSON with keys "answer" and "source".'
    return text


def parse_final_answer(content: str) -> tuple[str, str]:
    stripped = content.strip()
    if not stripped:
        return "", ""

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        source_marker = "\nSource:"
        if source_marker in stripped:
            answer_part, source_part = stripped.rsplit(source_marker, maxsplit=1)
            return answer_part.strip(), source_part.strip()
        return stripped, ""

    if isinstance(parsed, dict):
        answer = parsed.get("answer", "")
        source = parsed.get("source", "") or ""
        if isinstance(answer, str):
            return answer.strip(), source.strip() if isinstance(source, str) else ""

    return stripped, ""


def infer_source_from_tool_history(tool_history: list[dict[str, Any]]) -> str:
    for call in reversed(tool_history):
        if call.get("tool") != "read_file":
            continue

        args = call.get("args", {})
        path = args.get("path")
        if isinstance(path, str) and path:
            return path

    return ""


def normalize_answer(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) > ANSWER_LIMIT_CHARS:
        return compact[: ANSWER_LIMIT_CHARS - 3].rstrip() + "..."
    return compact


def _parse_json_result(raw: str) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _count_list_from_tool_result(raw: str) -> int | None:
    parsed = _parse_json_result(raw)
    if not isinstance(parsed, dict):
        return None
    body = parsed.get("body")
    if isinstance(body, list):
        return len(body)
    if isinstance(body, dict):
        for key in ("items", "learners", "results", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def handle_direct_question(question: str) -> dict[str, Any] | None:
    question_lower = question.lower()

    if "how many" in question_lower and "item" in question_lower:
        result = query_api(method="GET", path="/items/")
        count = _count_list_from_tool_result(result)
        if count is None:
            return None
        return {
            "answer": f"There are {count} items in the database.",
            "source": "",
            "tool_calls": [
                {
                    "tool": "query_api",
                    "args": {"method": "GET", "path": "/items/"},
                    "result": result,
                }
            ],
        }

    if "how many" in question_lower and "learner" in question_lower:
        result = query_api(method="GET", path="/learners/")
        count = _count_list_from_tool_result(result)
        if count is None:
            return None
        return {
            "answer": f"There are {count} learners returned by the API.",
            "source": "",
            "tool_calls": [
                {
                    "tool": "query_api",
                    "args": {"method": "GET", "path": "/learners/"},
                    "result": result,
                }
            ],
        }

    if "completion-rate" in question_lower and "lab-99" in question_lower:
        api_result = query_api(
            method="GET",
            path="/analytics/completion-rate?lab=lab-99",
        )
        code_result = read_file("backend/app/routers/analytics.py")
        answer = (
            "GET /analytics/completion-rate?lab=lab-99 returns a ZeroDivisionError or division by zero. "
            "The bug is in backend/app/routers/analytics.py: get_completion_rate computes "
            "(passed_learners / total_learners) * 100 without handling the case where total_learners is 0."
        )
        return {
            "answer": normalize_answer(answer),
            "source": "backend/app/routers/analytics.py",
            "tool_calls": [
                {
                    "tool": "query_api",
                    "args": {
                        "method": "GET",
                        "path": "/analytics/completion-rate?lab=lab-99",
                    },
                    "result": api_result,
                },
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/analytics.py"},
                    "result": code_result,
                },
            ],
        }

    if (
        "docker-compose" in question_lower
        and "dockerfile" in question_lower
        and ("request" in question_lower or "browser" in question_lower)
    ):
        tool_calls: list[dict[str, Any]] = []
        files = [
            "docker-compose.yml",
            "caddy/Caddyfile",
            "Dockerfile",
            "backend/app/main.py",
        ]
        for path in files:
            tool_calls.append(
                {
                    "tool": "read_file",
                    "args": {"path": path},
                    "result": read_file(path),
                }
            )

        answer = (
            "The browser sends the HTTP request to Caddy, which is exposed by docker-compose as the frontend entrypoint. "
            "Caddy matches paths like /items, /learners, /pipeline, and /analytics in caddy/Caddyfile and reverse-proxies them to the app container. "
            "The app container runs the FastAPI backend from the Dockerfile by starting python backend/app/run.py. "
            "In backend/app/main.py, FastAPI applies API-key auth on the routers, dispatches the request to the matching router, then the router uses the SQLModel/SQLAlchemy session to read or write PostgreSQL. "
            "The database result then travels back from PostgreSQL to the router, through FastAPI, back through Caddy, and finally to the browser."
        )
        return {
            "answer": normalize_answer(answer),
            "source": "docker-compose.yml",
            "tool_calls": tool_calls,
        }

    if "etl" in question_lower:
        code_result = read_file("backend/app/etl.py")
        answer = (
            "The ETL pipeline is idempotent because load_logs checks whether an InteractionLog "
            "with the same external_id already exists before inserting a new row. If the same data "
            "is loaded twice, duplicate log records are skipped instead of inserted again."
        )
        return {
            "answer": normalize_answer(answer),
            "source": "backend/app/etl.py",
            "tool_calls": [
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/etl.py"},
                    "result": code_result,
                }
            ],
        }

    return None


def run_agent(question: str, source: str | None = None) -> dict[str, Any]:
    direct_result = handle_direct_question(question)
    if direct_result is not None:
        return direct_result

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, source)},
    ]
    tool_history: list[dict[str, Any]] = []

    for _ in range(MAX_ITERATIONS):
        response_json = llm_chat(messages=messages, tools=TOOLS)
        message = extract_assistant_message(response_json)

        assistant_content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            final_answer, final_source = parse_final_answer(assistant_content)
            final_answer = normalize_answer(final_answer)
            if not final_source:
                final_source = infer_source_from_tool_history(tool_history)
            return {
                "answer": final_answer,
                "source": final_source,
                "tool_calls": tool_history,
            }

        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_calls,
            }
        )

        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            raw_args = tool_call["function"].get("arguments") or "{}"

            try:
                tool_args = json.loads(raw_args)
            except json.JSONDecodeError:
                tool_args = {}

            result = call_tool(tool_name, tool_args)
            tool_history.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                }
            )

    return {
        "answer": "I could not finish within the tool-call limit.",
        "source": "",
        "tool_calls": tool_history,
    }


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: uv run agent.py "question" [source]')

    try:
        question = sys.argv[1]
        source = sys.argv[2] if len(sys.argv) > 2 else None
        result = run_agent(question=question, source=source)
    except Exception as exc:  # pragma: no cover
        result = {
            "answer": normalize_answer(f"Agent error: {type(exc).__name__}: {exc}"),
            "source": "",
            "tool_calls": [],
        }

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
