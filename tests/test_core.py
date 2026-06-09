import os
import subprocess
import re
from utils import ask_hermes, ask_hermes_with_tools, DATA_DIR

def test_data_volume_writable():
    test_file = os.path.join(DATA_DIR, ".write-test-python")
    with open(test_file, "w") as f:
        f.write("test")
    assert os.path.exists(test_file)
    os.remove(test_file)

def test_dependencies_installed():
    """Verify system dependencies exist in the container."""
    for cmd in ["jq", "git", "xvfb-run", "chromium", "gh", "gws"]:
        result = subprocess.run(["which", cmd], capture_output=True, text=True)
        assert result.returncode == 0, f"Dependency missing: {cmd}"

def test_basic_prompt():
    response = ask_hermes("reply with just the word PONG")
    assert "PONG" in response

def test_headless_browser_load():
    response, tools = ask_hermes_with_tools(
        "use your browser to navigate to https://example.com and tell me the page title"
    )
    assert "Example Domain" in response, f"Expected 'Example Domain' in: {response}"
    assert any("browser" in t or "navigate" in t for t in tools), \
        f"Expected a browser tool to be used, got: {tools}"

def test_headless_browser_extract_json():
    response, tools = ask_hermes_with_tools(
        "navigate to https://httpbin.org/get and return the value of the url field from the JSON"
    )
    assert "httpbin.org" in response, f"Expected 'httpbin.org' in: {response}"
    assert any("browser" in t or "navigate" in t for t in tools), \
        f"Expected a browser tool to be used, got: {tools}"

def test_execute_python_code():
    response, tools = ask_hermes_with_tools(
        "execute this python code and give me the output: print(2 ** 10)"
    )
    assert "1024" in response, f"Expected '1024' in: {response}"
    assert any("python" in t or "execute" in t or "terminal" in t or "shell" in t or "run" in t for t in tools), \
        f"Expected a code execution tool, got: {tools}"

def test_execute_shell_code():
    response, tools = ask_hermes_with_tools(
        "run this shell command and give me the output: echo 'pytest-ok'"
    )
    assert "pytest-ok" in response, f"Expected 'pytest-ok' in: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools), \
        f"Expected a shell execution tool, got: {tools}"

def test_write_file():
    test_file = os.path.join(DATA_DIR, "pytest-test-write.txt")
    if os.path.exists(test_file):
        os.remove(test_file)

    _, tools = ask_hermes_with_tools(
        "write a file at /opt/data/pytest-test-write.txt containing exactly: hello-from-pytest"
    )

    assert os.path.exists(test_file), "Agent failed to create the file"
    with open(test_file) as f:
        content = f.read()
    assert "hello-from-pytest" in content, f"File content was: {content}"
    assert any("write" in t or "file" in t or "shell" in t or "terminal" in t for t in tools), \
        f"Expected a file-write tool, got: {tools}"

def test_read_file():
    test_file = os.path.join(DATA_DIR, "pytest-test-read.txt")
    with open(test_file, "w") as f:
        f.write("read-test-content")

    response, tools = ask_hermes_with_tools(
        "read the file at /opt/data/pytest-test-read.txt and tell me its contents"
    )
    assert "read-test-content" in response, f"Expected content in: {response}"
    assert any("read" in t or "file" in t or "shell" in t or "terminal" in t for t in tools), \
        f"Expected a file-read tool, got: {tools}"

def test_fetch_vix_via_yfinance():
    response, tools = ask_hermes_with_tools(
        "write and execute python code to fetch the current ^VIX price from Yahoo Finance using yfinance and print just the number"
    )
    assert re.search(r'[0-9]+', response) is not None, f"Response did not contain a number: {response}"
    assert any("python" in t or "execute" in t or "terminal" in t or "shell" in t or "run" in t for t in tools), \
        f"Expected a code execution tool, got: {tools}"
