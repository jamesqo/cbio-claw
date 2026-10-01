"""Optional preset tests against the private vault and pinned Hermes."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cbio_claw.vault import install, read_manifest, resolve_preset


@unittest.skipUnless(os.environ.get("CBIO_TEST_VAULT"), "Set CBIO_TEST_VAULT to the private configuration checkout")
class RealVaultTests(unittest.TestCase):
    def test_both_presets_install_current_support_and_engineering_with_references(self):
        source = Path(os.environ["CBIO_TEST_VAULT"])
        manifest = read_manifest(source)
        support = resolve_preset(manifest, "researcher-support")
        engineering = resolve_preset(manifest, "engineering")
        self.assertIn("cbioportal-answer-support", support)
        self.assertNotIn("cbioportal-answer-support", engineering)
        self.assertIn("cbio-stack", engineering)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            install(source, data, "engineering", {"CTEST": "researcher-support"})
            for name in set(support + engineering):
                original = source / manifest["skills"][name]
                installed = data / "skills/cbio-claw" / name
                for file in original.rglob("*"):
                    if file.is_file():
                        self.assertEqual(file.read_bytes(), (installed / file.relative_to(original)).read_bytes())
            self.assertIn("cbio-stack", (data / "skills/cbio-claw/cbio-stack/SKILL.md").read_text())

    @unittest.skipUnless(os.environ.get("HERMES_TEST_SOURCE"), "Requires pinned Hermes skill discovery")
    def test_installed_presets_are_discoverable_by_real_hermes(self):
        from tools import skills_tool
        source = Path(os.environ["CBIO_TEST_VAULT"])
        manifest = read_manifest(source)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for preset in ("researcher-support", "engineering"):
                expected = set(install(source, data, preset, {}))
                with patch.object(skills_tool, "SKILLS_DIR", data / "skills"):
                    result = json.loads(skills_tool.skills_list())
                self.assertTrue(result["success"])
                self.assertEqual({skill["name"] for skill in result["skills"]}, expected)
                self.assertEqual(expected, set(resolve_preset(manifest, preset)))
