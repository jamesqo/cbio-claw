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


@unittest.skipUnless(os.environ.get("HERMES_TEST_SOURCE"), "Set HERMES_TEST_SOURCE to the pinned Hermes checkout")
class HermesIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_attachment_only_message_without_text_field(self):
        await self.check_attachment_only_message(False)

    async def test_attachment_only_message_with_empty_text_field(self):
        await self.check_attachment_only_message(True)

    async def test_real_adapter_slackbot_file_share_downloads_email_and_posts(self):
        import httpx
        real_client = httpx.AsyncClient
        requests = []
        def transport(request):
            requests.append(request)
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>How do I export MET alterations?</p>")
        with patch("httpx.AsyncClient", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)):
            await self.check_attachment_only_message(True, file_only=True)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].headers["authorization"], "Bearer xoxb-test")

    async def check_attachment_only_message(self, include_empty_text, file_only=False):
        from gateway.config import PlatformConfig
        from gateway.platforms.slack import SlackAdapter
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HERMES_HOME": directory}):
            Path(directory, "cbio-claw.json").write_text(json.dumps({"mailing_list": {"enabled": True, "channels": {"CTEST": {"forwarder_bot_ids": ["BEMAIL"], "forwarder_user_ids": ["USLACKBOT"]}}}}))
            adapter = SlackAdapter(PlatformConfig(enabled=True, extra={"allowed_channels": ["CTEST"], "channel_skill_bindings": [{"id": "CTEST", "skills": ["cbioportal-answer-support", "cbioportal-support"]}]}))
            adapter._bot_user_id = "USELF"
            adapter._message_handler = AsyncMock(return_value="💡 *Suggested response:*\nA test answer.")
            client = SimpleNamespace(token="xoxb-test", chat_postMessage=AsyncMock(return_value={"ok": True, "ts": "2.0"}), files_info=AsyncMock(return_value={"ok": True, "file": {"mimetype": "text/html", "size": 1000, "url_private": "https://files.slack.com/files-pri/T-F/email.html"}}))
            adapter._get_client = lambda channel: client
            mailing.install_adapter(SlackAdapter)
            event = {"type": "message", "channel": "CTEST", "bot_id": "BEMAIL", "subtype": "bot_message", "ts": "1.0", "attachments": [{"text": "Where can I download study data?"}]}
            if file_only:
                event = {"type": "message", "channel": "CTEST", "user": "USLACKBOT", "subtype": "file_share", "ts": "1.0", "files": [{"id": "FEMAIL"}]}
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
            if file_only:
                self.assertIn("How do I export MET alterations?", message.text)
                client.files_info.assert_awaited_once_with(file="FEMAIL")
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
