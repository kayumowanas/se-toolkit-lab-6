# Task 3 Plan — The System Agent

## Goal

Extend the existing agent with a new `query_api` tool so it can answer:

- wiki/documentation questions
- source-code/system questions
- live backend/data questions

## Tool design

I will add a `query_api` function-calling tool with:

- `method`: HTTP method such as GET or POST
- `path`: API path such as `/items/`
- `body`: optional JSON string for request body

The tool will:

- read `AGENT_API_BASE_URL` from environment variables
- default to `http://localhost:42002` if missing
- read `LMS_API_KEY` from environment variables
- send the API key in request headers
- return a JSON string with `status_code` and `body`

## Authentication

I will use:

- `LMS_API_KEY` for the backend API
- `LLM_API_KEY` only for the LLM provider

I will not hardcode secrets or URLs.

## Prompt update

I will update the system prompt so the agent:

- uses `read_file` for source code and wiki details
- uses `list_files` to discover relevant files/modules
- uses `query_api` for live system facts and data-dependent queries

## Benchmark strategy

First I will run `uv run run_eval.py` once.
Then I will record:

- initial score
- first failing questions
- likely cause
- fix strategy

## Iteration notes

Initial score: not run yet in this workspace snapshot
First failures: unknown until `run_eval.py` is executed with valid autochecker credentials
Fix strategy:

- first make the output contract stable: `answer`, optional `source`, `tool_calls`
- add a deterministic mock LLM mode so regression tests do not depend on a real provider
- keep `read_file` and `list_files` compatible with Task 2 while extending the agent with `query_api`
- improve the system prompt so the model distinguishes:
  - wiki/documentation questions
  - source-code questions
  - live API and runtime-error questions
- run the benchmark question by question, starting with the first failing index
- if the model chooses the wrong tool, tighten the tool descriptions and add clearer prompt rules
- if the answer is correct but misses a keyword, make the final answer wording more explicit
