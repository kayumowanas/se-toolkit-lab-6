# Task 2 Plan — The Documentation Agent

## Goal

Extend the Task 1 CLI agent with tools that allow it to read project documentation.

The agent will:

1. Accept a user question from the command line
2. Send the question and tool schemas to the LLM
3. Execute tool calls requested by the LLM
4. Feed the results back to the LLM
5. Stop when the LLM returns a final answer

The final output JSON will include:

- answer
- source
- tool_calls

## Tools

### list_files

Lists files and directories at a given path relative to the project root.

Input:
- path (string)

Output:
- newline-separated list of entries

### read_file

Reads a file from the repository.

Input:
- path (string)

Output:
- file contents as text

## Path Security

Tools must prevent access outside the repository.

Implementation:

- resolve paths using Path.resolve()
- ensure the resolved path is inside the project root
- reject paths with ../ traversal

## Agentic Loop

The agent will:

1. Send messages + tools to the LLM
2. If the LLM returns tool_calls:
   - execute tools
   - append tool results as messages
   - call LLM again
3. If the LLM returns a normal text message:
   - extract answer and source
   - output JSON
4. Stop after a maximum of 10 tool calls.

## Output Format

The CLI outputs JSON:

{
  "answer": "...",
  "source": "wiki/file.md#section",
  "tool_calls": [...]
}

## Testing

Two regression tests will verify:

1. "How do you resolve a merge conflict?"
   - tool_calls include read_file
   - source references wiki/git-workflow.md

2. "What files are in the wiki?"
   - tool_calls include list_files
