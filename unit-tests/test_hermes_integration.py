"""Optional tests against the exact Hermes source and private vault, without connections."""

import json
import asyncio
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from cbio_claw import mailing
from cbio_claw.integrate import integrate
from cbio_claw.vault import install, read_manifest, resolve_preset


@unittest.skipUnless(os.environ.get("HERMES_TEST_SOURCE"), "Set HERMES_TEST_SOURCE to the pinned Hermes checkout")
class HermesIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_attachment_only_message_without_text_field(self):
        await self.check_attachment_only_message(False)

    async def test_attachment_only_message_with_empty_text_field(self):
        await self.check_attachment_only_message(True)

    async def check_attachment_only_message(self, include_empty_text):
        from gateway.config import PlatformConfig
        from gateway.platforms.slack import SlackAdapter
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HERMES_HOME": directory}):
            Path(directory, "cbio-claw.json").write_text(json.dumps({"mailing_list": {"enabled": True, "channels": {"CTEST": {"forwarder_bot_ids": ["BEMAIL"]}}}}))
            adapter = SlackAdapter(PlatformConfig(enabled=True, extra={"allowed_channels": ["CTEST"], "channel_skill_bindings": [{"id": "CTEST", "skills": ["cbioportal-answer-support", "cbioportal-support"]}]}))
            adapter._bot_user_id = "USELF"
            adapter._message_handler = AsyncMock(return_value="💡 *Suggested response:*\nA test answer.")
            client = SimpleNamespace(chat_postMessage=AsyncMock(return_value={"ok": True, "ts": "2.0"}))
            adapter._get_client = lambda channel: client
            mailing.install_adapter(SlackAdapter)
            event = {"type": "message", "channel": "CTEST", "bot_id": "BEMAIL", "subtype": "bot_message", "ts": "1.0", "attachments": [{"text": "Where can I download study data?"}]}
            if include_empty_text:
                event["text"] = ""
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.request.async_request import AsyncBoltRequest
            app = AsyncApp(token="xoxb-test")
            @app.event("message")
            async def handle_message_event(event, say):
                await adapter._handle_slack_message(event)
            request = AsyncBoltRequest(body={"type": "event_callback", "team_id": "TTEST", "event": event}, mode="socket_mode")
            self.assertTrue(await app._async_listeners[0].async_matches(req=request, resp=None))
            await adapter._handle_slack_message(event)
            await adapter._handle_slack_message(event)
            await asyncio.gather(*list(adapter._cbio_mailing_tasks))
            adapter._message_handler.assert_awaited_once()
            message = adapter._message_handler.call_args.args[0]
            self.assertTrue(message.source.is_bot)
            self.assertTrue(message.internal)
            self.assertEqual(message.source.thread_id, "1.0")
            self.assertEqual(message.auto_skill, ["cbioportal-answer-support", "cbioportal-support"])
            client.chat_postMessage.assert_awaited_once()
            self.assertEqual(client.chat_postMessage.call_args.kwargs["thread_ts"], "1.0")

    def test_build_hooks_validate_actual_pinned_source_and_are_idempotent(self):
        import shutil
        source = Path(os.environ["HERMES_TEST_SOURCE"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ("gateway/platforms/slack.py", "gateway/run.py"):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, target)
            integrate(root)
            first = (root / "gateway/run.py").read_text()
            integrate(root)
            self.assertEqual((root / "gateway/run.py").read_text(), first)
            self.assertLess(first.index("install_gateway(globals())"), first.rindex('if __name__ == "__main__":'))


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
