"""Register the Daikon deployment sidecar on the engineering profile."""

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

profile = Path("/opt/data/profiles/engineering")
config = profile / "config.yaml"
runtime_note = (
    "Runtime: execute shell commands locally and use the direct Playwright MCP for browser "
    "work. Use the cBioPortal deployment MCP for disposable backend and study deployments "
    "on Daikon. The Docker daemon is available only to the MCP sidecar. Use public "
    "CircleCI reports for frontend E2E triage. Existing external portal services may be "
    "accessed by URL."
)
integration = "/opt/data/cbio-deployment"
entry = {
    "command": "/usr/local/bin/node",
    "args": [f"{integration}/deployment-mcp-relay.mjs", "client", f"{integration}/mcp.sock"],
    "timeout": 3600,
    "connect_timeout": 45,
}
original = config.read_text()
settings = yaml.safe_load(original)
servers = settings.setdefault("mcp_servers", {})
skills = settings.setdefault("skills", {})


def update(path, previous, content):
    if previous == content:
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.stem}.before-deployment-mcp-{timestamp}{path.suffix}")
    with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        stream.write(previous)
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    temporary.replace(path)
    print(f"Updated {path.name}. Backup: {backup}")


servers["cbio_deployment"] = entry
disabled = skills.get("disabled") or []
if isinstance(disabled, str):
    disabled = [disabled]
if "cbio-acceptance-testing" not in disabled:
    skills["disabled"] = [*disabled, "cbio-acceptance-testing"]
if settings != yaml.safe_load(original):
    update(config, original, yaml.safe_dump(settings, sort_keys=False))

soul = profile / "SOUL.md"
original = soul.read_text()
paragraphs = original.split("\n\n")
for index, paragraph in enumerate(paragraphs):
    if paragraph.startswith("Runtime: execute shell commands locally") and "deployment MCP" in paragraph:
        paragraphs[index] = runtime_note
        break
else:
    paragraphs.append(runtime_note)
update(soul, original, "\n\n".join(paragraphs))
