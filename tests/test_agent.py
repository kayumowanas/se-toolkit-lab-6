import json
import os
import subprocess
import sys


def test_agent_output():
    env = os.environ.copy()

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
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)
