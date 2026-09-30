import json
from pathlib import Path
import tempfile
import unittest

import yaml

from cbio_claw.vault import install, read_manifest


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.data = self.root / "data"
        for name in ("shared", "support", "engineering"):
            skill = self.vault / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Test skill\n---\nInstructions.\n")
        refs = self.vault / "skills/support/references"
        refs.mkdir()
        (refs / "formats.md").write_text("A real reference file.")
        self.manifest = {
            "version": 1,
            "skills": {n: "skills/" + n for n in ("shared", "support", "engineering")},
            "modules": {n: [n] for n in ("shared", "support", "engineering")},
            "presets": {
                "researcher-support": {"modules": ["shared", "support"], "auto_skills": ["support"]},
                "engineering": {"modules": ["shared", "engineering"], "auto_skills": ["engineering"]},
            },
        }
        self.write_manifest()

    def write_manifest(self):
        (self.vault / "presets.json").write_text(json.dumps(self.manifest))

    def test_switch_presets_preserves_unmanaged_skills_and_references(self):
        other = self.data / "skills/operator-skill"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: operator-skill\n---\nKeep me.")
        install(self.vault, self.data, "researcher-support", {})
        self.assertEqual((self.data / "skills/cbio-claw/support/references/formats.md").read_text(), "A real reference file.")
        install(self.vault, self.data, "engineering", {})
        self.assertTrue((other / "SKILL.md").exists())
        self.assertFalse((self.data / "skills/cbio-claw/support").exists())
        self.assertTrue((self.data / "skills/cbio-claw/engineering/SKILL.md").exists())

    def test_channels_install_union_and_only_replace_requested_bindings(self):
        self.data.mkdir()
        config = {"model": {"model": "keep"}, "slack": {"allow_bots": "none", "extra": {"keep": True}, "channel_skill_bindings": [{"id": "COTHER", "skills": ["custom"]}, {"id": "CSUPPORT", "skills": ["old"]}]}}
        path = self.data / "config.yaml"
        original = yaml.safe_dump(config)
        path.write_text(original)
        selected = install(self.vault, self.data, "engineering", {"CSUPPORT": "researcher-support"})
        self.assertEqual(set(selected), {"shared", "support", "engineering"})
        result = yaml.safe_load(path.read_text())
        self.assertEqual(result["model"], config["model"])
        self.assertEqual(result["slack"]["allow_bots"], "none")
        self.assertEqual(result["slack"]["extra"], {"keep": True})
        self.assertIn({"id": "COTHER", "skills": ["custom"]}, result["slack"]["channel_skill_bindings"])
        self.assertIn({"id": "CSUPPORT", "skills": ["support"]}, result["slack"]["channel_skill_bindings"])
        self.assertEqual(path.with_suffix(".yaml.before-presets").read_text(), original)

    def test_identical_existing_skill_is_reused_and_not_rewritten(self):
        import shutil
        installed = self.data / "skills/support"
        shutil.copytree(self.vault / "skills/support", installed)
        before = (installed / "SKILL.md").stat().st_mtime_ns
        install(self.vault, self.data, "researcher-support", {})
        self.assertFalse((self.data / "skills/cbio-claw/support").exists())
        self.assertEqual((installed / "SKILL.md").stat().st_mtime_ns, before)

    def test_different_existing_skill_fails_before_mutation(self):
        other = self.data / "skills/operator"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: support\n---\nDifferent.")
        with self.assertRaisesRegex(ValueError, "collides"):
            install(self.vault, self.data, "researcher-support", {})
        self.assertFalse((self.data / "skills/cbio-claw").exists())

    def test_unmanaged_destination_is_not_overwritten(self):
        target = self.data / "skills/cbio-claw"
        target.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            install(self.vault, self.data, "engineering", {})

    def test_invalid_selection_does_not_create_data(self):
        with self.assertRaisesRegex(ValueError, "Unknown preset"):
            install(self.vault, self.data, "typo", {})
        with self.assertRaisesRegex(ValueError, "Slack channel ID"):
            install(self.vault, self.data, "engineering", {"#engineering": "engineering"})
        self.assertFalse(self.data.exists())

    def test_escaping_skill_path_is_rejected(self):
        self.manifest["skills"]["shared"] = "../outside"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "escapes"):
            read_manifest(self.vault)
