# Task 3 Plan — The System Agent


## Goal

Extend the documentation agent with a new `query_api` tool so it can answer questions using:
- project wiki files,
- repository source code,
- the live backend API.

The agent will keep the Task 2 agentic loop and add one more tool schema.

## New tool: query_api

The `query_api` tool will call the deployed backend API.

Parameters:
- `method` (string) — HTTP method such as GET or POST
- `path` (string) — API path such as `/items/`
- `body` (string, optional) — JSON request body

The tool will return a JSON string with:
- `status_code`
- `body`

## Authentication

`query_api` will authenticate using `LMS_API_KEY` from environment variables.

The base URL will come from:
- `AGENT_API_BASE_URL`
- defaulting to `http://localhost:42002`

No values will be hardcoded because the autochecker injects its own configuration.

## Tool selection strategy

The system prompt will instruct the LLM to:
- use `read_file` and `list_files` for wiki and source code questions,
- use `query_api` for live system and data questions,
- combine `query_api` and `read_file` for bug diagnosis questions,
- always keep answers grounded in tool results.

## Agent loop

The Task 2 loop will be reused:
1. send messages + tool schemas to the LLM,
2. execute any tool calls,
3. append tool results,
4. continue until final answer,
5. stop after a maximum number of tool calls.

## Benchmark plan

I will run `uv run run_eval.py` after implementing `query_api`.

Initial benchmark score:
- not run yet

Expected likely failures:
- wrong tool selection
- incomplete source diagnosis
- missing API authentication
- content truncation when reading large files

Iteration strategy:
1. run the benchmark,
2. inspect the first failing question,
3. improve tool descriptions or the system prompt,
4. fix any implementation bugs,
5. repeat until all 10 local questions pass.
