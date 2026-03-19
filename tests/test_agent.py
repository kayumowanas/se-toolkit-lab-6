import json
import os
import subprocess
import sys


def test_agent_output():
    env = os.environ.copy()
    env["LLM_API_KEY"] = "test-key"
    env["LLM_API_BASE"] = "https://example.com/v1"
    env["LLM_MODEL"] = "test-model"

    # mock LLM response so test does not call real API
    env["MOCK_LLM_RESPONSE"] = "Representational State Transfer."

    result = subprocess.run(
        [sys.executable, "agent.py", "What does REST stand for?"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0

    data = json.loads(result.stdout)

    assert "answer" in data
    assert "source" in data
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)
