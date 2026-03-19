import json
import os
import subprocess
import sys


def run_agent(question: str, responses: list[dict]) -> dict:
    env = os.environ.copy()
    env["LLM_API_KEY"] = "test-key"
    env["LLM_API_BASE"] = "https://example.com/v1"
    env["LLM_MODEL"] = "test-model"
    env["MOCK_LLM_RESPONSES"] = json.dumps(responses)

    result = subprocess.run(
        [sys.executable, "agent.py", question],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_merge_conflict_question_uses_read_file() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "list_files",
                                    "arguments": json.dumps({"path": "wiki"}),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps(
                                        {"path": "wiki/git-workflow.md"}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": (
                                    "Edit the conflicting file, choose which changes "
                                    "to keep, then stage and commit."
                                ),
                                "source": (
                                    "wiki/git-workflow.md#resolving-merge-conflicts"
                                ),
                            }
                        ),
                    }
                }
            ]
        },
    ]

    data = run_agent("How do you resolve a merge conflict?", responses)

    assert data["source"] == "wiki/git-workflow.md#resolving-merge-conflicts"
    assert any(call["tool"] == "read_file" for call in data["tool_calls"])


def test_what_files_are_in_the_wiki_uses_list_files() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "list_files",
                                    "arguments": json.dumps({"path": "wiki"}),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "The wiki contains documentation files.",
                                "source": "wiki",
                            }
                        ),
                    }
                }
            ]
        },
    ]

    data = run_agent("What files are in the wiki?", responses)

    assert any(call["tool"] == "list_files" for call in data["tool_calls"])
    assert data["source"] == "wiki"


def test_framework_question_uses_read_file() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "backend/app/main.py"}),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "The backend uses FastAPI.",
                                "source": "backend/app/main.py",
                            }
                        ),
                    }
                }
            ]
        },
    ]

    data = run_agent("What framework does the backend use?", responses)

    assert data["answer"] == "The backend uses FastAPI."
    assert data["source"] == "backend/app/main.py"
    assert any(call["tool"] == "read_file" for call in data["tool_calls"])


def test_item_count_question_uses_query_api() -> None:
    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "query_api",
                                    "arguments": json.dumps(
                                        {"method": "GET", "path": "/items/"}
                                    ),
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer": "There are 120 items in the database.",
                                "source": "",
                            }
                        ),
                    }
                }
            ]
        },
    ]

    data = run_agent("How many items are in the database?", responses)

    assert data["answer"] == "There are 120 items in the database."
    assert any(call["tool"] == "query_api" for call in data["tool_calls"])
