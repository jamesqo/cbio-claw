"""Compose skills from shared modules without replacing an existing vault."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

import yaml


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(contents)
        if path.exists():
            os.chmod(name, path.stat().st_mode & 0o777)
            if os.geteuid() == 0:
                os.chown(name, path.stat().st_uid, path.stat().st_gid)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def read_manifest(vault: Path) -> dict:
    manifest = json.loads((vault / "presets.json").read_text())
    if manifest.get("version") != 1:
        raise ValueError("Unsupported skill-vault manifest version")
    for names in manifest["modules"].values():
        for name in names:
            if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
                raise ValueError(f"Invalid skill name: {name!r}")
            relative = Path(manifest["skills"][name])
            skill_dir = vault / relative
            if relative.is_absolute() or ".." in relative.parts or vault.resolve() not in skill_dir.resolve().parents:
                raise ValueError(f"Skill path escapes vault: {relative}")
            skill = skill_dir / "SKILL.md"
            if not skill.is_file():
                raise ValueError(f"Missing skill: {skill}")
            frontmatter = yaml.safe_load(skill.read_text().split("---", 2)[1])
            if frontmatter.get("name") != name or not frontmatter.get("description"):
                raise ValueError(f"Invalid skill frontmatter: {skill}")
    for preset in manifest["presets"]:
        names = resolve_preset(manifest, preset)
        if not set(manifest["presets"][preset]["auto_skills"]) <= set(names):
            raise ValueError(f"Auto-loaded skills are not in preset: {preset}")
    return manifest


def resolve_preset(manifest: dict, preset: str) -> list[str]:
    if preset not in manifest["presets"]:
        raise ValueError(f"Unknown preset {preset!r}; choose {', '.join(manifest['presets'])}")
    names = []
    for module in manifest["presets"][preset]["modules"]:
        for name in manifest["modules"][module]:
            if name not in names:
                names.append(name)
    return names


def install(vault: Path, data_dir: Path, preset: str, channels: dict[str, str]) -> list[str]:
    manifest = read_manifest(vault)
    selected = resolve_preset(manifest, preset)
    for channel, channel_preset in channels.items():
        if not channel.startswith(("C", "G", "D")) or not channel.isalnum():
            raise ValueError(f"Use a Slack channel ID, not a channel name: {channel!r}")
        selected.extend(resolve_preset(manifest, channel_preset))
    selected = list(dict.fromkeys(selected))
    config_path = data_dir / "config.yaml"
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("Hermes config must be a YAML mapping")
    slack = config.setdefault("slack", {})
    if not isinstance(slack, dict):
        raise ValueError("slack configuration must be a mapping")
    bindings = slack.get("channel_skill_bindings", [])
    if not isinstance(bindings, list):
        raise ValueError("slack.channel_skill_bindings must be a list")
    for channel, channel_preset in channels.items():
        # Only explicitly selected channels are changed; preserve other bindings.
        bindings = [b for b in bindings if not isinstance(b, dict) or str(b.get("id")) != channel]
        bindings.append({"id": channel, "skills": manifest["presets"][channel_preset]["auto_skills"]})
    if channels:
        slack["channel_skill_bindings"] = bindings

    target = data_dir / "skills" / "cbio-claw"
    marker = target / ".managed.json"
    if target.exists() and not marker.is_file():
        raise ValueError(f"Refusing to replace unmanaged skills at {target}")
    # Avoid duplicate names with skills installed by the operator.
    skills_root = data_dir / "skills"
    reused = []
    for skill in skills_root.rglob("SKILL.md") if skills_root.exists() else []:
        if target in skill.parents:
            continue
        parts = skill.read_text().split("---", 2)
        meta = yaml.safe_load(parts[1]) if len(parts) == 3 else {}
        if isinstance(meta, dict) and meta.get("name") in selected:
            name = meta["name"]
            source = vault / manifest["skills"][name]
            expected = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            actual = {str(p.relative_to(skill.parent)): p.read_bytes() for p in skill.parent.rglob("*") if p.is_file()}
            if expected != actual or name in reused:
                raise ValueError(f"Skill name collides with a different or duplicate installed skill: {skill}")
            reused.append(name)

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=target.parent, prefix=".cbio-claw-"))
    try:
        for name in selected:
            if name not in reused:
                shutil.copytree(vault / manifest["skills"][name], staging / name)
        (staging / ".managed.json").write_text(json.dumps({"preset": preset, "channels": channels, "skills": selected, "reused": reused}, indent=2) + "\n")
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if channels:
        # YAML is rewritten only when channel bindings were requested.
        if config_path.exists() and not config_path.with_suffix(".yaml.before-presets").exists():
            shutil.copy2(config_path, config_path.with_suffix(".yaml.before-presets"))
        atomic_write(config_path, yaml.safe_dump(config, sort_keys=False))
    if os.geteuid() == 0:
        # The upstream init can skip chown when the data root already has the
        # requested UID. Only fix files this installer owns, not the whole vault.
        uid = int(os.environ.get("HERMES_UID") or data_dir.stat().st_uid)
        gid = int(os.environ.get("HERMES_GID") or data_dir.stat().st_gid)
        for path in [target, *target.rglob("*")]:
            os.chown(path, uid, gid)
        if channels:
            os.chown(config_path, uid, gid)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=Path("/opt/cbio-claw/vault"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--channel", action="append", default=[], metavar="CHANNEL_ID=PRESET")
    args = parser.parse_args()
    channels = json.loads(os.environ.get("CBIO_SKILL_CHANNELS") or "{}")
    if not isinstance(channels, dict):
        parser.error("CBIO_SKILL_CHANNELS must be a JSON object mapping Slack channel IDs to presets")
    for binding in args.channel:
        channel, separator, preset = binding.partition("=")
        if not separator:
            parser.error("--channel requires CHANNEL_ID=PRESET")
        channels[channel] = preset
    try:
        selected = install(args.vault, args.data_dir, args.preset, channels)
    except (ValueError, KeyError, yaml.YAMLError) as error:
        parser.error(str(error))
    print(json.dumps({"preset": args.preset, "channels": channels, "skills": selected}, indent=2))


if __name__ == "__main__":
    main()
