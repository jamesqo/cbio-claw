from utils import ask_hermes_with_tools

def test_github_auth_via_agent():
    response, tools = ask_hermes_with_tools(
        "run this shell command and give me the output: gh auth status"
    )
    assert "Logged in to github.com" in response or "Token" in response, f"Expected GitHub auth success in: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools)

def test_github_recent_prs():
    response, tools = ask_hermes_with_tools(
        "use the gh cli to list my recent PRs. if there are none, explicitly state 'no prs'"
    )
    assert "error" not in response.lower() or "no prs" in response.lower(), f"Agent encountered an error: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools), \
        f"Expected a shell execution tool, got: {tools}"

def test_github_list_repos():
    response, tools = ask_hermes_with_tools(
        "use the gh cli to list 3 of my repositories"
    )
    assert "error" not in response.lower() or "no repos" in response.lower(), f"Agent encountered an error: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools), \
        f"Expected a shell execution tool, got: {tools}"

def test_github_gists():
    response, tools = ask_hermes_with_tools(
        "use the gh cli to list my gists. if there are none, explicitly state 'no gists'"
    )
    assert "error" not in response.lower() or "no gists" in response.lower(), f"Agent encountered an error: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools), \
        f"Expected a shell execution tool, got: {tools}"

def test_github_organizations():
    response, tools = ask_hermes_with_tools(
        "use the gh cli or api to list the organizations I am a member of. if there are none, explicitly state 'no organizations'"
    )
    assert "error" not in response.lower() or "no organizations" in response.lower(), f"Agent encountered an error: {response}"
    assert any("shell" in t or "terminal" in t or "execute" in t or "run" in t for t in tools), \
        f"Expected a shell execution tool, got: {tools}"
