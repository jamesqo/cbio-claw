"""Install small import-time hooks into the pinned Hermes source during image build."""

import argparse
import ast
from pathlib import Path


def integrate(root: Path):
    patches = [
        (root / "gateway/platforms/slack.py", "SlackAdapter", "_handle_slack_message",
         "from cbio_claw.mailing import install_adapter\ninstall_adapter(SlackAdapter)\n"),
        (root / "gateway/run.py", None, "_load_gateway_config",
         "from cbio_claw.mailing import install_gateway\ninstall_gateway(globals())\n"),
    ]
    for path, cls, function, hook in patches:
        source = path.read_text()
        tree = ast.parse(source)
        nodes = tree.body
        if cls:
            classes = [n for n in nodes if isinstance(n, ast.ClassDef) and n.name == cls]
            nodes = classes[0].body if classes else []
        if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function for n in nodes):
            raise ValueError(f"Unsupported Hermes source at {path}: {function} missing")
        if hook not in source:
            lines = source.splitlines(keepends=True)
            guards = [n for n in tree.body if isinstance(n, ast.If) and ast.unparse(n.test) == "__name__ == '__main__'"]
            position = guards[0].lineno - 1 if guards else len(lines)
            lines.insert(position, "\n\n" + hook + "\n")
            source = "".join(lines)
            compile(source, str(path), "exec")
            path.write_text(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", type=Path, required=True)
    integrate(parser.parse_args().hermes_root)
