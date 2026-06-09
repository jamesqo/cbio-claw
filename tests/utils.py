import os
import requests
import json
import pytest
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GATEWAY_URL = os.environ.get("HERMES_GATEWAY_URL", "http://hermes-gateway:8642/v1")
BASE_URL = GATEWAY_URL.replace("/v1", "")
API_KEY = "test-integration-key"
AUTH = {"Authorization": f"Bearer {API_KEY}"}
DATA_DIR = "/opt/data"

client = OpenAI(base_url=GATEWAY_URL, api_key=API_KEY)

TEST_INSTRUCTIONS = (
    "You are being tested in an integration test environment. "
    "Prefer tools and libraries that are already installed on the system. "
    "If you install any package (pip, apt, npm, brew, etc.) during your work, "
    "you MUST output a line at the very start of your response formatted exactly as: "
    "INSTALLED: <package_name>. Output one INSTALLED: line per package installed. "
    "If you cannot complete the task for any reason (fatal missing dependency, permission error, etc.), "
    "ESPECIALLY if you run into an authorization error from any service you're using, "
    "respond with exactly: TEST_FAIL: <one-line reason>. "
    "Do not add any other text when signalling a failure."
)

FAIL_PREFIX = "TEST_FAIL:"
INSTALL_PREFIX = "INSTALLED:"

# Accumulated across the session — reported in the terminal summary fixture.
_installs: list[str] = []

def _check_for_agent_failure(response: str) -> None:
    """If the agent signalled a failure, propagate it as a pytest failure."""
    stripped = response.strip()
    if stripped.startswith(FAIL_PREFIX):
        reason = stripped[len(FAIL_PREFIX):].strip()
        pytest.fail(f"Agent reported failure: {reason}")


def _check_for_installs(response: str) -> None:
    """Detect INSTALLED: lines, record them, and fail the test if any are found."""
    found = []
    for line in response.splitlines():
        s = line.strip()
        if s.startswith(INSTALL_PREFIX):
            pkg = s[len(INSTALL_PREFIX):].strip()
            found.append(pkg)
            _installs.append(pkg)
    if found:
        pytest.fail(f"Agent installed packages during test: {', '.join(found)}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ask_hermes(prompt: str) -> str:
    """Send a prompt via the OpenAI-compatible endpoint, print and return the response."""
    response = client.chat.completions.create(
        model="hermes-agent",
        messages=[
            {"role": "system", "content": TEST_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ]
    )
    content = response.choices[0].message.content
    print(f"\n  [response] {content}")
    _check_for_agent_failure(content)
    _check_for_installs(content)
    return content


def ask_hermes_with_tools(prompt: str) -> tuple[str, list[str]]:
    """
    Send a prompt via the /v1/runs + /v1/runs/{id}/events SSE API.
    Returns (final_response_text, [tool_names_called]).
    This lets tests assert both the answer AND which tools the agent used.
    """
    # Start the run (runs API uses `input`, not `messages`)
    resp = requests.post(
        f"{BASE_URL}/v1/runs",
        json={"model": "hermes-agent", "input": prompt, "instructions": TEST_INSTRUCTIONS},
        headers=AUTH,
        timeout=10,
    )
    resp.raise_for_status()
    run_id = resp.json()["run_id"]

    # Stream SSE events until stream closes
    tools_started: list[str] = []
    deltas: list[str] = []

    with requests.get(
        f"{BASE_URL}/v1/runs/{run_id}/events",
        headers={**AUTH, "Accept": "text/event-stream"},
        stream=True,
        timeout=120,
    ) as stream:
        for raw_line in stream.iter_lines():
            if not raw_line or not raw_line.startswith(b"data: "):
                continue
            try:
                event = json.loads(raw_line[6:])
            except json.JSONDecodeError:
                continue
            evt = event.get("event", "")
            if evt == "tool.started":
                tool = event.get("tool", "")
                preview = event.get("preview", "")
                tools_started.append(tool)
                print(f"\n  [tool] {tool}  args: {preview}", flush=True)
            elif evt == "message.delta":
                deltas.append(event.get("delta", ""))

    final_text = "".join(deltas)
    print(f"\n  [response] {final_text}")
    print(f"  [tools used] {tools_started}")
    _check_for_agent_failure(final_text)
    _check_for_installs(final_text)
    return final_text, tools_started
