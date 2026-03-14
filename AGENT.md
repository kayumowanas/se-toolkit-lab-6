# AGENT

## Overview

This project implements a minimal CLI agent that sends a user question to an OpenAI-compatible LLM and returns a JSON response.

The agent accepts a question as a command line argument, calls the LLM API, and prints a structured JSON response.

Example:

uv run agent.py "What does REST stand for?"

Example output:

{"answer": "Representational State Transfer.", "tool_calls": []}

## LLM Provider

The agent uses an OpenAI-compatible API.

Recommended provider: **Qwen Code API**

Recommended model:

qwen3-coder-plus

## Configuration

The agent reads configuration from `.env.agent.secret`.

Required variables:

LLM_API_KEY  
LLM_API_BASE  
LLM_MODEL

Example `.env.agent.secret`:

LLM_API_KEY=your_api_key_here  
LLM_API_BASE=https://api.qwen.ai/v1  
LLM_MODEL=qwen3-coder-plus

## Output format

The agent prints a single JSON object to stdout with the fields:

answer — string  
tool_calls — array

Example:

{"answer": "Representational State Transfer.", "tool_calls": []}

For Task 1 the `tool_calls` array is always empty.

## Error handling

Errors are printed to stderr.

Exit code:
- 0 on success
- non-zero on failure

## Running the agent

Example:

uv run agent.py "What does REST stand for?"

## Running tests

pytest


