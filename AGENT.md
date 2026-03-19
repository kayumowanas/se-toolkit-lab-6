# AGENT

## Overview

This project implements a CLI coding agent that answers questions about the repository and the running backend. The agent accepts a natural-language question from the command line, sends the conversation and tool schemas to an OpenAI-compatible chat-completions API, executes tool calls, and prints one JSON object to stdout.

The final JSON has three fields:

- `answer`: the final natural-language answer
- `source`: the file or wiki reference used for the answer when a source is available
- `tool_calls`: the full tool trace, where each entry contains `tool`, `args`, and `result`

This format supports both Task 2 and Task 3. For documentation questions, `source` usually points to a wiki file or section anchor. For live system questions, `source` may be empty because the answer comes from the running backend rather than a repository file.

## Configuration

The agent reads configuration from environment variables instead of hardcoding credentials or URLs.

- `LLM_API_KEY`: authentication token for the LLM provider
- `LLM_API_BASE`: base URL for the OpenAI-compatible API
- `LLM_MODEL`: chat model name
- `LMS_API_KEY`: API key used to authenticate requests to the deployed backend
- `AGENT_API_BASE_URL`: base URL for `query_api`, defaulting to `http://localhost:42002`

Two different keys are used for different systems. `LLM_API_KEY` is only for the chat model. `LMS_API_KEY` is only for the backend API. Mixing them would cause either LLM requests or backend requests to fail.

The local `.env.agent.secret` and `.env.docker.secret` files are only convenience files for development. The agent itself depends on environment variables so it can run correctly in the autochecker with injected values.

## Tools

The agent exposes three tools to the model.

`read_file` reads a text file from inside the repository. It is used for wiki answers, framework questions, Docker and architecture questions, ETL inspection, and code-based bug diagnosis. Paths are resolved relative to the project root, and traversal outside the repository is rejected.

`list_files` lists repository files under a relative directory. It is mainly used as a discovery step when the model needs to find a wiki page or identify backend router modules before calling `read_file`.

`query_api` sends an HTTP request to the running backend and returns a JSON string with `status_code` and `body`. By default it authenticates with `Authorization: Bearer <LMS_API_KEY>`. It can also disable auth for questions about unauthenticated behavior, such as checking which status code `/items/` returns without a header.

## Tool-selection strategy

The system prompt teaches the model to separate three classes of questions.

- Wiki and documentation questions should use `read_file`, sometimes after `list_files`.
- Source-code and architecture questions should inspect real code with `read_file`, not answer from memory.
- Live runtime and data questions should use `query_api`.

For runtime bugs, the intended flow is two-step: first reproduce the error with `query_api`, then inspect the responsible source file with `read_file`. This matters for Task 3 because some benchmark questions require both the observed error and the bug in the code. The prompt also tells the model to mention concrete exception names such as `ZeroDivisionError` or `TypeError` instead of vague phrasing.

## Agent loop and testing

The agent uses a standard tool-calling loop. It sends the user question and tools to the model, executes any returned tool calls, appends the tool results back into the message history, and repeats until the model returns a final answer or the tool-call limit is reached. The current limit is 10 iterations.

To keep regression tests deterministic, the agent supports mock modes through `MOCK_LLM_RESPONSE` and `MOCK_LLM_RESPONSES`. These environment variables let the tests simulate either a single final response or a multi-step tool-calling conversation without contacting a real provider.

The most important lesson from Task 3 was that passing hidden benchmark questions requires a genuinely working tool-selection strategy, not hardcoded answers. The output contract also needs to stay stable across tasks: Task 2 still expects `source`, while Task 3 adds `query_api` and allows system answers with an empty source. The remaining benchmark work is to run `uv run run_eval.py`, record the first failures, and iterate on prompt precision and tool descriptions until the local evaluation passes fully.
