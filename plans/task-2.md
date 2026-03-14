# Task 2 Plan — The Documentation Agent

## Goal

Extend the CLI agent so it can answer repository documentation questions by using tools.

The agent will:
1. accept a user question from the command line,
2. send the question and tool schemas to an OpenAI-compatible LLM,
3. execute tool calls returned by the LLM,
4. feed tool results back into the conversation,
5. stop when the LLM returns a final answer,
6. print JSON with:
   - answer
   - source
   - tool_calls

## Tools

### list_files
Lists files and directories at a relative path from the project root.

Input:
- path (string)

Output:
- newline-separated directory contents
- or an error string

### read_file
Reads a file from a relative path from the project root.

Input:
- path (string)

Output:
- file contents
- or an error string

## Path security

Both tools will resolve paths relative to the project root and reject:
- absolute paths
- traversal outside the repository, including ../

This will be enforced using Path.resolve() and checking that the resolved path stays inside the project root.

## Agentic loop

The program will:
1. send the user question + system prompt + tool schemas to the LLM,
2. if the LLM returns tool_calls:
   - execute them,
   - append tool results as tool messages,
   - repeat,
3. if the LLM returns a normal assistant response:
   - parse the final answer and source,
   - return JSON and exit,
4. stop after a maximum of 10 tool calls.

## Output format

The final stdout JSON will contain:
- answer (string)
- source (string)
- tool_calls (array)

## Testing

Two regression tests will be added:
1. "How do you resolve a merge conflict?"
   - expects read_file in tool_calls
   - expects source to include wiki/git-workflow.md
2. "What files are in the wiki?"
   - expects list_files in tool_calls
